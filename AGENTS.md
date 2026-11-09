# Contract authority ownership

This repository owns only durable non-financial organization self-use contracts.
The plane authenticates the person and verifies membership, host ownership and
admission. Do not add billing, payments, AIuditor policy/execution, fake
certification or a successful fallback when authority/storage is unavailable.

Run `bash scripts/check-package.sh`; source, wheel and rebuilt sdist must execute
the same tests without skips. Preserve the one-hour original expiry across retries.

Never create or change version tags or publish/promote/replace/delete releases
without explicit owner approval for that specific action. Preparing artifacts,
merging code and continuing work are not release authorization. Do not add human
approval gates, required reviewers or branch protection without a specific owner
request. Private CI uses `[self-hosted, linux, x64, debrunner]`.

## Service deployments and binary provenance

Each TEST service automatically tracks the latest PR merged into its repository's default branch. Deploy the tested build through a moving TEST channel. Do not pin running services to versions, commit SHAs or image digests, require manual pin updates, or require peer services to run matching builds. Preserve patch compatibility, including during early development, and verify it through the service contract.

Use exact versions and digests for downloadable bundles and to record or verify which binary was built, tested or released. A running service may report its revision for diagnostics. Production follows its existing promotion policy and explicit release authorization.
