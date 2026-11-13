from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import psycopg
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from hypermesh_contract_authority import create_app, Fulfill, Ledger

TOKEN = "local-test-only-authority-key-32-chars"


def terms(**extra):
    return {"lease_id": str(uuid4()), "reserved_hours": 1, "renter_subject": str(uuid4()),
            "host_subject": str(uuid4()), "meters": ["wall_time", "capacity_block"], **extra}


@pytest.fixture
def storage():
    dsn = os.environ["AUTHORITY_TEST_DATABASE_URL"]
    ledger = Ledger(dsn, migrate=True)
    with ledger.connect() as db:
        db.execute("TRUNCATE contracts")
    return dsn


def test_restart_and_concurrent_replay_are_identical(storage):
    tenant = uuid4(); body = Fulfill(**terms())
    first = Ledger(storage).fulfill(tenant, body)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: Ledger(storage).fulfill(tenant, body), range(16)))
    assert all(row == first for row in rows)
    assert datetime.fromisoformat(first["until"]) - datetime.fromisoformat(first["signed_at"]) == timedelta(hours=1)
    assert first["rail"] == "self-use"
    with psycopg.connect(storage) as db:
        assert db.execute("SELECT count(*) FROM contracts").fetchone()[0] == 1


def test_no_renewal_or_unknown_claimed_contract(storage):
    tenant = uuid4(); body = Fulfill(**terms()); ledger = Ledger(storage)
    now = datetime.now(UTC); first = ledger.fulfill(tenant, body, now)
    assert ledger.fulfill(tenant, body, now + timedelta(minutes=59)) == first
    with pytest.raises(HTTPException) as expired:
        ledger.fulfill(tenant, body, now + timedelta(hours=1))
    assert expired.value.status_code == 409
    with pytest.raises(HTTPException) as absent:
        ledger.fulfill(uuid4(), body.model_copy(update={"contract_id": first["id"]}))
    assert absent.value.status_code == 404


@pytest.mark.parametrize("field", ["renter_subject", "host_subject"])
def test_replay_cannot_change_parties(storage, field):
    tenant = uuid4(); body = Fulfill(**terms()); ledger = Ledger(storage)
    ledger.fulfill(tenant, body)
    with pytest.raises(HTTPException) as conflict:
        ledger.fulfill(tenant, body.model_copy(update={field: uuid4()}))
    assert conflict.value.status_code == 409


def test_tenant_isolation_and_contract_id_binding(storage):
    ledger = Ledger(storage); body = Fulfill(**terms()); tenant = uuid4()
    first = ledger.fulfill(tenant, body)
    assert ledger.fulfill(uuid4(), body)["id"] != first["id"]
    assert ledger.fulfill(tenant, body.model_copy(update={"contract_id": first["id"]})) == first
    with pytest.raises(HTTPException):
        ledger.fulfill(tenant, body.model_copy(update={"contract_id": uuid4()}))


@pytest.mark.parametrize("patch", [{"reserved_hours": 2}, {"reserved_hours": True}, {"reserved_hours": "1"},
    {"meters": ["wall_time", "wall_time"]}, {"meters": ["token_digest_count"]},
    {"rail": "stripe"}, {"gross_cents": 1}, {"renter_subject": "unbound"}])
def test_invalid_or_financial_requests_never_write(storage, patch):
    with TestClient(create_app(dsn=storage, token=TOKEN)) as client:
        result = client.post("/v1/contracts/fulfill", headers={"X-Tenant-ID": str(uuid4()), "X-Internal-Token": TOKEN}, json=terms(**patch))
        assert result.status_code == 422
    with psycopg.connect(storage) as db:
        assert db.execute("SELECT count(*) FROM contracts").fetchone()[0] == 0


def test_authentication_and_missing_tenant(storage):
    with TestClient(create_app(dsn=storage, token=TOKEN)) as client:
        for token in (None, "wrong-key"):
            headers = {"X-Tenant-ID": str(uuid4())}
            if token: headers["X-Internal-Token"] = token
            assert client.get("/v1/meta", headers=headers).status_code == 401
            assert client.post("/v1/contracts/fulfill", headers=headers, json=terms()).status_code == 401
        assert client.post("/v1/contracts/fulfill", headers={"X-Internal-Token": TOKEN}, json=terms()).status_code == 422
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/v1/meta", headers={"X-Internal-Token": TOKEN}).json()["financial"] is False
        # No market-writer compatibility route and no financial API.
        assert client.get("/api/v1/aiuditor/meta").status_code == 404


def test_corrupt_storage_and_weak_configuration_fail_closed(storage):
    with pytest.raises(ValueError): create_app(dsn=storage, token="weak")
    with TestClient(create_app(dsn=storage, token=TOKEN)) as client:
        with psycopg.connect(storage) as db: db.execute("DROP TABLE contracts")
        result = client.post("/v1/contracts/fulfill", headers={"X-Tenant-ID": str(uuid4()), "X-Internal-Token": TOKEN}, json=terms())
        assert result.status_code == 503
        assert client.get("/health").status_code == 503
        assert TOKEN not in result.text and str(storage) not in result.text


@pytest.mark.parametrize("dsn", ["", ":memory:", "file:/tmp/contracts", "/data/contracts"])
def test_non_postgres_configuration_refused(dsn):
    with pytest.raises(ValueError): Ledger(dsn)


def test_unreachable_database_never_starts():
    with pytest.raises(psycopg.OperationalError):
        create_app(dsn="postgresql://invalid:invalid@127.0.0.1:1/invalid", token=TOKEN)


def test_simultaneous_first_fulfill(storage):
    from threading import Barrier
    tenant, body = uuid4(), Fulfill(**terms())
    ledgers = [Ledger(storage), Ledger(storage)]
    barrier = Barrier(2)
    def call(ledger):
        barrier.wait(timeout=10)
        return ledger.fulfill(tenant, body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(call, ledgers))
    assert rows[0] == rows[1]
    with psycopg.connect(storage) as db:
        assert db.execute("SELECT count(*) FROM contracts").fetchone()[0] == 1


def test_import_atomic_and_idempotent(storage, tmp_path):
    import sqlite3
    import runpy
    importer = runpy.run_path(str(Path(__file__).parent.parent / "tools/import_contracts.py"))["import_contracts"]
    ledger = Ledger(storage)
    ledger.fulfill(uuid4(), Fulfill(**terms()))
    with ledger.connect() as db:
        rows = db.execute("SELECT * FROM contracts").fetchall()
        db.execute("TRUNCATE contracts")
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE contracts (tenant, lease, id, request, record)")
        db.executemany("INSERT INTO contracts VALUES (?,?,?,?,?)", rows)
    assert importer(source, storage) == importer(source, storage) == 1
    with ledger.connect() as db:
        assert db.execute("SELECT * FROM contracts").fetchall() == rows
        db.execute("TRUNCATE contracts")
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO contracts VALUES ('bad','bad','bad','bad','bad')")
    with pytest.raises(ValueError): importer(source, storage)
    with ledger.connect() as db:
        assert db.execute("SELECT count(*) FROM contracts").fetchone()[0] == 0
    source.write_bytes(b"corrupt database")
    with pytest.raises(sqlite3.DatabaseError): importer(source, storage)


def test_runtime_starts_without_schema_privileges(storage):
    from psycopg import sql
    role = "test_runtime_" + uuid4().hex
    with psycopg.connect(storage, autocommit=True) as db:
        db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        try:
            db.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("GRANT SELECT,INSERT ON contracts TO {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("CREATE TABLE forbidden_runtime_table(id integer)")
            db.execute("SELECT tenant,lease,id,request,record FROM contracts LIMIT 0")
        finally:
            db.execute("RESET ROLE")
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_service_package_has_no_legacy_store():
    import inspect
    import hypermesh_contract_authority
    source = inspect.getsource(hypermesh_contract_authority)
    assert "sqlite" not in source.lower()
    assert "CONTRACT_AUTHORITY_DB" not in source


def test_remote_database_transport_always_verifies_tls(monkeypatch):
    from unittest.mock import patch
    monkeypatch.delenv("CONTRACT_AUTHORITY_TEST_DATABASE", raising=False)
    ledger = object.__new__(Ledger)
    ledger.dsn = "postgresql://owner:secret@database.example/authority?sslmode=disable"
    with patch("hypermesh_contract_authority.psycopg.connect") as connect:
        ledger.connect()
    assert connect.call_args.kwargs["sslmode"] == "verify-full"
    monkeypatch.setenv("CONTRACT_AUTHORITY_TEST_DATABASE", "1")
    with pytest.raises(ValueError): ledger.connect()
