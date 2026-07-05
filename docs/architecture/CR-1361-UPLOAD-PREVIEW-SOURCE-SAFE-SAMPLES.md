# CR-1361: Upload Preview Source-Safe Samples

Date: 2026-07-05

## Objective

Fix GitHub issue #590 by making bulk upload preview responses source-safe by default and gating
sample-row disclosure behind a signed privileged capability with redaction.

## Findings

Upload preview returned normalized valid rows by default. Those rows can contain portfolio,
client-adjacent, instrument, transaction, quantity, price, fee, tax, and amount fields. Callers
usually need validation counts and row errors, not full source row content.

## Actions Taken

1. Changed `UploadPreviewCommand` to default `include_sample_rows=false`.
2. Changed `UploadIngestionService.preview_upload(...)` to return `sample_rows=[]` by default.
3. Added redaction for sensitive identifiers, monetary, fee, tax, price, quantity, notional, and
   market-value fields when privileged sample rows are explicitly requested.
4. Added `include_sample_rows` form input to `/ingest/uploads/preview`.
5. Added a forced capability check for `ingestion.uploads.preview_samples.read` using the signed
   enterprise auth-context contract, independent of whether global authz is enabled.
6. Added allow/deny audit events for preview sample-row access.
7. Updated OpenAPI descriptions and focused unit/integration tests for default minimization,
   privileged redaction, capability denial, audit evidence, and schema truth.

## Expected Improvement

Preview callers get validation summaries and correction errors without receiving sensitive source
row content. Operators who need diagnostic samples must present a signed service-principal context
with the dedicated sample capability, and the returned rows are still redacted.

## Compatibility

The response field `sample_rows` remains present for downstream compatibility, but defaults to an
empty list. Existing callers that only consume counts and errors are unaffected. Callers that relied
on default row samples must opt in with `include_sample_rows=true` and the signed
`ingestion.uploads.preview_samples.read` capability.

No commit-upload behavior, Kafka topic, database schema, route path, Dockerfile, or runtime
topology changed.

## Validation Evidence

```powershell
python -m pytest tests\unit\services\ingestion_service\services\test_upload_ingestion_service.py tests\unit\services\ingestion_service\routers\test_uploads.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_upload_parameters_and_shared_schemas tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_accepts_all_supported_entity_families tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_transactions_csv tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_limits_sample_rows_and_errors -q
python -m pytest tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py::test_authorize_request_rejects_forged_capability_headers_without_signature tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py::test_authorize_request_rejects_forged_service_identity_signature tests\unit\services\ingestion_service\test_enterprise_readiness.py::test_ingestion_write_requires_route_capability -q
python -m ruff check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py src\services\ingestion_service\app\enterprise_readiness.py src\services\ingestion_service\app\application\upload_commands.py src\services\ingestion_service\app\services\upload_ingestion_service.py src\services\ingestion_service\app\routers\uploads.py src\services\ingestion_service\app\DTOs\upload_dto.py tests\unit\services\ingestion_service\services\test_upload_ingestion_service.py tests\unit\services\ingestion_service\routers\test_uploads.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py src\services\ingestion_service\app\enterprise_readiness.py src\services\ingestion_service\app\application\upload_commands.py src\services\ingestion_service\app\services\upload_ingestion_service.py src\services\ingestion_service\app\routers\uploads.py src\services\ingestion_service\app\DTOs\upload_dto.py tests\unit\services\ingestion_service\services\test_upload_ingestion_service.py tests\unit\services\ingestion_service\routers\test_uploads.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
make quality-wiki-docs-gate
make security-control-coverage-guard
$env:PYTHONPATH = "src/services/ingestion_service;src/libs/portfolio-common"; python -c "import app.main; print('ingestion app import ok')"
git diff --check
```

Results: 23 upload-focused tests and 3 enterprise auth regressions passed; scoped Ruff, format
check, wiki/docs gate, security-control coverage guard, and ingestion app import proof passed.
`git diff --check` passed with expected CRLF normalization warnings only.

## Documentation Decision

Repo-local context, security docs, security wiki source, and the codebase review ledger were updated
because the upload preview response contract changed from default sample disclosure to default
source-safe minimization. No platform-wide skill change is required; this is pinned by repo-local
tests and OpenAPI descriptions.
