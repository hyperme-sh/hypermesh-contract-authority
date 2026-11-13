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

PostgreSQL stores a unique tenant/lease binding in the authority's own database.
Transaction-scoped locks preserve the original record across concurrent requests
and process restarts. Deployment applies an additive table migration with a separate migration role.
Runtime startup only checks the existing schema and fails when storage is unavailable. There is no fallback store.

Run with Python 3.13 and uv:

```sh
uv sync --frozen --no-dev
# Generate your own secret file; use a private directory and keep its value out of logs.
export CONTRACT_AUTHORITY_TOKEN_FILE=/absolute/private/path/authority-token
export CONTRACT_AUTHORITY_DATABASE_URL_FILE=/run/secrets/authority-database-url
# Deployment step with the separate migration credential:
CONTRACT_AUTHORITY_MIGRATION_URL_FILE=/run/secrets/authority-migration-url uv run --frozen --no-dev hypermesh-contract-authority-migrate
uv run --frozen --no-dev hypermesh-contract-authority
```

Deliver the connection URL from a Key Vault reference into a private mounted file.
Use the authority owner role and its database only. Connections always enforce
`sslmode=verify-full`; deliver a trusted CA file through `sslrootcert` in the URL
or the libpq CA setting. The explicit `CONTRACT_AUTHORITY_TEST_DATABASE=1` setting
allows plaintext only to loopback or the declared TEST PostgreSQL container host;
it is for isolated CI/TEST networks and must not be set in production. Generate at least 32 random secret
characters locally and share the token only with the trusted plane. The service
listens on port 8080; keep it on a private service network or protect transport
with TLS. `/health` reports storage availability and requires no token.

A `signed` record means the authenticated plane attested a self-use request and
the authority committed its terms. It is not an asymmetric signature, payment
receipt, hardware certification, independent auditor verdict, or legal signature.
There are no billing, payment, general-purpose policy, model-inspection or
AI execution endpoints. Those owners remain outside this package.

Package CI runs source, wheel and rebuilt-source contracts against its disposable
PostgreSQL service with no skips. Full composition belongs to the central nightly
batch. Main publishes the qualified container to
`ghcr.io/hyperme-sh/hypermesh-contract-authority/runtime:test`; TEST follows that
moving channel independently of peer releases.

For TEST cutover, stop new fulfillment on the old owner and wait until all
one-hour original contracts have expired before starting on an empty PostgreSQL
database. Preserve the old store for rollback investigation. If any unexpired
contract remains, stop writes and use the separate operator tool before cutover:

```sh
uv run python tools/import_contracts.py /private/legacy.db --connection-file /run/secrets/authority-database-url
```

The tool reads a consistent legacy snapshot, validates all rows and imports in
one transaction. Repeating an identical import changes nothing; conflicting or
corrupt input fails without partial records. IDs, parties and timestamps remain
unchanged. The legacy reader is outside the service package and runtime image.
After accepting new PostgreSQL writes, rollback must retain this database; never
return to an older file that lacks those contracts.
