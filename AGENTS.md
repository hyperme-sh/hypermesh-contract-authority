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

## Integration and receipt runs

No agent runs integration tests or functional API receipts by hand on hosts
or other shared resources, and none run those suites outside CI. On a pull
request, agents run only unit and contract tests. CI may add a smoke check
scoped to the services the pull request touches. A toggle or configuration
change needs a unit or contract test for that change, not a full receipt or
end-to-end suite.

The full integration suite runs once as a nightly CI batch against main.
That batch uses a single concurrency group and cancels any run it supersedes.
When a nightly run fails on something whose issue is already closed, CI files
a new issue for that failure and links the closed issue when one exists.

Receipts and full integration results are not a Product Sign-off gate. Green
CI and clean reviews are enough for Sign-off.

Authorized CI workflows, including test-bundle publication and existing smoke
or owner-integration jobs, may keep running in CI. Agents must not start or
repeat those jobs by hand on shared hosts.

## Service deployments and binary provenance

Each TEST service automatically tracks the latest PR merged into its repository's default branch. Deploy the tested build through a moving TEST channel. Do not pin running services to versions, commit SHAs or image digests, require manual pin updates, or require peer services to run matching builds. Preserve patch compatibility, including during early development, and verify it through the service contract.

Use exact versions and digests for downloadable bundles and to record or verify which binary was built, tested or released. A running service may report its revision for diagnostics. Production follows its existing promotion policy and explicit release authorization.
