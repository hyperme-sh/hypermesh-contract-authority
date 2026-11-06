from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
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
def storage(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700)
    return root / "contracts.sqlite3"


def test_restart_and_concurrent_replay_are_identical(storage):
    tenant = uuid4(); body = Fulfill(**terms())
    first = Ledger(storage).fulfill(tenant, body)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: Ledger(storage).fulfill(tenant, body), range(16)))
    assert all(row == first for row in rows)
    assert datetime.fromisoformat(first["until"]) - datetime.fromisoformat(first["signed_at"]) == timedelta(hours=1)
    assert first["rail"] == "self-use"
    with sqlite3.connect(storage) as db:
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
    with TestClient(create_app(path=storage, token=TOKEN)) as client:
        result = client.post("/v1/contracts/fulfill", headers={"X-Tenant-ID": str(uuid4()), "X-Internal-Token": TOKEN}, json=terms(**patch))
        assert result.status_code == 422
    with sqlite3.connect(storage) as db:
        assert db.execute("SELECT count(*) FROM contracts").fetchone()[0] == 0


def test_authentication_and_missing_tenant(storage):
    with TestClient(create_app(path=storage, token=TOKEN)) as client:
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
    with pytest.raises(ValueError): create_app(path=storage, token="weak")
    with TestClient(create_app(path=storage, token=TOKEN)) as client:
        with sqlite3.connect(storage) as db: db.execute("DROP TABLE contracts")
        result = client.post("/v1/contracts/fulfill", headers={"X-Tenant-ID": str(uuid4()), "X-Internal-Token": TOKEN}, json=terms())
        assert result.status_code == 503
        assert TOKEN not in result.text and str(storage) not in result.text


def test_insecure_storage_directory_refused(tmp_path):
    root = tmp_path / "public"; root.mkdir(mode=0o755)
    with pytest.raises(ValueError): Ledger(root / "contracts.sqlite3")
