"""A separate durable authority for non-financial self-use contracts.

Only the authenticated plane may attest verified membership/host eligibility.
This authority records that attestation; it does not certify hardware, assert
payment, or impersonate an AIuditor market writer.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hmac
import json
import os
from pathlib import Path
import psycopg
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

PROTOCOL = "hypermesh-self-use-contract/1"
SIGNER = "organization-self-use-authority"


class Fulfill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: UUID
    reserved_hours: StrictInt = Field(ge=1, le=1)
    renter_subject: UUID
    host_subject: UUID
    meters: list[Literal["wall_time", "capacity_block"]] = Field(min_length=2, max_length=2)
    contract_id: UUID | None = None


class Ledger:
    def __init__(self, dsn: str, *, migrate: bool = False):
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("A PostgreSQL connection URL is required")
        self.dsn = dsn
        with self.connect() as db:
            if migrate:
                # Only the deployment migrator receives DDL credentials.
                db.execute("SELECT pg_advisory_xact_lock(743286192)")
                db.execute("CREATE TABLE IF NOT EXISTS contracts (tenant TEXT NOT NULL, lease TEXT NOT NULL, id TEXT NOT NULL UNIQUE, request TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY(tenant,lease))")
            else:
                db.execute("SELECT tenant,lease,id,request,record FROM contracts LIMIT 0")


    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=10)

    def fulfill(self, tenant: UUID, body: Fulfill, now: datetime | None = None):
        if set(body.meters) != {"wall_time", "capacity_block"}:
            raise HTTPException(422, "Self-use requires wall_time and capacity_block")
        clock = now or datetime.now(UTC)
        request = json.dumps(body.model_dump(mode="json", exclude={"contract_id"}) | {"meters": sorted(body.meters)}, sort_keys=True)
        with self.connect() as db:
            # A transaction-scoped key lock also covers the absent-row case.
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{tenant}:{body.lease_id}",))
            try:
                row = db.execute("SELECT request, record FROM contracts WHERE tenant=%s AND lease=%s", (str(tenant), str(body.lease_id))).fetchone()
                if row:
                    record = json.loads(row[1])
                    if row[0] != request or (body.contract_id and str(body.contract_id) != record["id"]):
                        raise HTTPException(409, "Lease already bound to different terms")
                    if datetime.fromisoformat(record["until"]) <= clock:
                        raise HTTPException(409, "Contract expired; replay cannot extend it")
                else:
                    if body.contract_id:
                        raise HTTPException(404, "Contract not found for this tenant and lease")
                    record = {
                        "id": str(uuid4()), "tenant_id": str(tenant), "lease_id": str(body.lease_id),
                        "parties": [{"role": "renter", "subject": str(body.renter_subject)}, {"role": "host", "subject": str(body.host_subject)}],
                        "meters": sorted(body.meters), "rail": "self-use", "status": "signed",
                        "signed_by": SIGNER, "signed_at": clock.isoformat(),
                        "until": (clock + timedelta(hours=1)).isoformat(), "protocol": PROTOCOL,
                    }
                    db.execute("INSERT INTO contracts VALUES (%s,%s,%s,%s,%s)", (str(tenant), str(body.lease_id), record["id"], request, json.dumps(record, sort_keys=True)))
                db.execute("COMMIT")
                return record
            except BaseException:
                db.execute("ROLLBACK")
                raise


def create_app(*, dsn: str, token: str) -> FastAPI:
    if len(token) < 32 or token.strip() != token:
        raise ValueError("A locally generated authority token of at least 32 characters is required")
    ledger = Ledger(dsn)
    app = FastAPI(title="Hypermesh self-use contract authority", docs_url=None, redoc_url=None)

    def authenticate(value):
        if not value or not hmac.compare_digest(value.encode(), token.encode()):
            raise HTTPException(401, "Authority authentication required")

    @app.get("/health")
    def health():
        with ledger.connect() as db:
            db.execute("SELECT count(*) FROM contracts").fetchone()
        return {"status": "ok"}

    @app.get("/v1/meta")
    def meta(x_internal_token: str | None = Header(default=None)):
        authenticate(x_internal_token)
        return {"protocol": PROTOCOL, "writer": "self-use", "financial": False}

    @app.post("/v1/contracts/fulfill")
    def fulfill(body: Fulfill, x_tenant_id: UUID = Header(), x_internal_token: str | None = Header(default=None)):
        authenticate(x_internal_token)
        try:
            return ledger.fulfill(x_tenant_id, body)
        except psycopg.Error:
            raise HTTPException(503, "Contract storage unavailable") from None

    return app


def main():
    import uvicorn
    token_file = os.environ.get("CONTRACT_AUTHORITY_TOKEN_FILE")
    if not token_file:
        raise ValueError("CONTRACT_AUTHORITY_TOKEN_FILE is required")
    token = Path(token_file).read_text().strip()
    connection_file = os.environ.get("CONTRACT_AUTHORITY_DATABASE_URL_FILE")
    if not connection_file:
        raise ValueError("CONTRACT_AUTHORITY_DATABASE_URL_FILE is required")
    dsn = Path(connection_file).read_text().strip()
    uvicorn.run(create_app(dsn=dsn, token=token), host="0.0.0.0", port=8080, access_log=False)


def migrate():
    connection_file = os.environ["CONTRACT_AUTHORITY_MIGRATION_URL_FILE"]
    Ledger(Path(connection_file).read_text().strip(), migrate=True)
