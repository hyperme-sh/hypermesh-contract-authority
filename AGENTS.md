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
