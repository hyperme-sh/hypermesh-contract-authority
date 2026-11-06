# Hypermesh self-use contract authority

An Apache-2.0, non-financial contract owner for organization self-use. It records
one-hour leases durably without private libraries, cloud accounts, or AIuditor.
The authenticated plane remains responsible for verifying the human's active
organization membership, enrolled host ownership, capacity and admission.

The API exposes authenticated `GET /v1/meta` and
`POST /v1/contracts/fulfill`. Send `X-Internal-Token` and `X-Tenant-ID`.
Fulfillment requires a UUID lease, renter and host; exactly one reserved hour;
and the `wall_time` and `capacity_block` meters. The authority assigns the
contract ID and expiry. It rejects financial fields, unknown explicit contract
IDs, changed parties, expired replay, and attempts to extend the original hour.

SQLite uses WAL, full synchronous commits, a private storage directory, and a
unique tenant/lease binding. Concurrent requests and process restarts return the
same committed record. Back up the entire database consistently using SQLite's
backup API; do not copy a live database without its WAL. A missing/corrupt owner
must never be replaced by a simulator in a deployment.

Run with Python 3.13 and uv:

```sh
uv sync --frozen --no-dev
# Generate your own secret file; use a private directory and keep its value out of logs.
export CONTRACT_AUTHORITY_TOKEN_FILE=/absolute/private/path/authority-token
export CONTRACT_AUTHORITY_DB=/absolute/private/path/contracts.sqlite3
uv run --frozen --no-dev hypermesh-contract-authority
```

The database directory must be mode 0700. Generate at least 32 random secret
characters locally and share the token only with the trusted plane. The service
listens on port 8080; keep it on a private service network or protect transport
with TLS. `/health` reports storage availability and requires no token.

A `signed` record means the authenticated plane attested a self-use request and
the authority committed its terms. It is not an asymmetric signature, payment
receipt, hardware certification, independent auditor verdict, or legal signature.
There are no billing, payment, general-purpose policy, model-inspection or
AI execution endpoints. Those owners remain outside this package.

`uv run pytest tests` tests storage, concurrency, authentication, replay and
isolation. Plane's anonymous qualification additionally tests the installed
HTTP client against a separate authority process and its durable restart.
No version tag or package/image release is published by these tests.
