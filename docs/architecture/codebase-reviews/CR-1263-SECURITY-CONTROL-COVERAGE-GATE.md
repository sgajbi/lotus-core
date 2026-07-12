# CR-1263 Security Control Coverage Gate

## Objective

Fix GitHub issue #591 by making HTTP security control coverage explicit and regression-blocking
for every `lotus-core` FastAPI app.

## Expected Improvement

The slice turns distributed security posture into a reusable platform pattern:

1. shared HTTP bootstrap now installs secure response headers and a deny-by-default CORS policy,
2. ingestion, event replay, and financial reconciliation apps now install the shared default
   enterprise audit/authorization/payload middleware with local-compatible default-disabled authz,
3. ingestion upload APIs now reject payloads above `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES`,
4. `contracts/security/security-control-coverage.v1.json` lists every FastAPI app and its required
   auth/audit, unauthenticated allowlist, header, CORS, metrics, payload, upload, secret/default,
   and safe-error control posture,
5. `make security-control-coverage-guard` blocks missing app entries and missing implementation
   anchors.

## Downstream Compatibility

Existing route paths, request DTOs, response DTOs, Kafka topics, database schema, and local authz
defaults are preserved. Oversized bulk upload files now return HTTP 413 with
`INGESTION_UPLOAD_TOO_LARGE`; the default byte limit is 5 MiB and can be configured with
`LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES`.

The new CORS default is fail-closed for browser cross-origin access unless
`LOTUS_HTTP_CORS_ALLOW_ORIGINS` is explicitly set. Metrics remain internal-open by default and
become bearer-protected when `LOTUS_METRICS_ACCESS_TOKEN` is set.

## Validation Evidence

- `make security-control-coverage-guard`: passed.
- `python -m pytest tests\unit\scripts\test_security_control_coverage_guard.py tests\unit\libs\portfolio-common\test_http_app_bootstrap.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\ingestion_service\test_settings.py -q`: 54 passed.
- `python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_payload_above_configured_limit -q`: 1 passed.
- `make lint`: passed, including the security-control coverage guard.
- `make typecheck`: passed.
- `make quality-wiki-docs-gate`: passed.
- `make security-audit`: passed with dependency consistency clean and no known vulnerabilities;
  local editable Lotus packages were skipped by `pip-audit` because they are not PyPI
  distributions.
- `git diff --check`: passed; Git reported expected CRLF normalization warnings on touched files.
- `powershell -ExecutionPolicy Bypass -File ..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`: failed because the published GitHub wiki is not synchronized
  with repo-authored wiki source. Drift reported on `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, `Outbox-Events.md`,
  `Security-and-Governance.md`, and `Validation-and-CI.md`. The first four are pre-existing
  publication drift; the last two are intentionally changed by this slice and need normal
  post-merge wiki publication from `main`.

## Documentation And Wiki Decision

Updated repo-local docs, scorecard, review ledger, operations runbook, security guide, repository
context, and wiki source pages `Security-and-Governance.md` and `Validation-and-CI.md`. Wiki
publication remains pending until this branch is merged and the governed repository wiki sync step
is run from `main`.
