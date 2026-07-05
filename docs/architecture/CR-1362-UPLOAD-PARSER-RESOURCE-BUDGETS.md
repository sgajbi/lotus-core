# CR-1362: Upload Parser Resource Budgets

Date: 2026-07-05

## Objective

Fix GitHub issue #589 by bounding bulk upload preview and commit work before and during parsing.

## Findings

The upload path already had a streaming byte guard, but parser work still had gaps: CSV and XLSX
rows were collected without row, column, or cell-length budgets; XLSX parsing materialized the whole
worksheet; preview had no parse-rate protection; and obvious content-type/extension mismatches were
not rejected before parser work.

## Actions Taken

1. Added upload parser budget settings for max rows, max columns, and max cell length.
2. Wired `BulkUploadValidator` through an explicit `UploadParserBudget`.
3. Reworked CSV parsing to iterate rows through budget checks.
4. Reworked XLSX parsing to stream `read_only` worksheet rows and close the workbook.
5. Added parser-budget rejection details with `INGESTION_UPLOAD_PARSER_BUDGET_EXCEEDED`.
6. Rejected supported-media content-type/extension mismatches before reading the file.
7. Enforced content-length when available before reading the body, while keeping streaming byte
   enforcement for multipart overhead and absent headers.
8. Added preview and commit rate checks before body parsing.
9. Updated repo context, upload boundary standard, security docs, operations runbook, and wiki
   source.

## Expected Improvement

Upload requests now have layered abuse protection: request-rate control, content-length guard,
streaming byte guard, parser row/column/cell budgets, content-type sanity checks, and source-safe
error responses. Large or malformed CSV/XLSX inputs should fail before consuming unbounded memory or
CPU.

## Compatibility

Normal small CSV/XLSX preview and commit calls keep the same route paths, form fields, DTOs, Kafka
topics, and publisher behavior. New failures are intentional for uploads that exceed configured
budgets, present a mismatched content type, or hit route rate limits.

No database schema, Kafka topic, Dockerfile, runtime topology, or downstream response model changed.

## Validation Evidence

```powershell
python -m pytest tests\unit\services\ingestion_service\services\test_upload_validation.py tests\unit\services\ingestion_service\test_settings.py tests\unit\services\ingestion_service\test_adapter_mode.py tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_payload_above_configured_limit tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_content_length_above_configured_limit tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_allows_upload_budget_above_generic_write_cap tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_rows_above_parser_budget tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_content_type_extension_mismatch tests\integration\services\ingestion_service\test_ingestion_routers.py::test_read_bounded_upload_content_stops_after_stream_exceeds_limit tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_declares_upload_400_contracts tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_upload_parameters_and_shared_schemas -q
python -m ruff check src\services\ingestion_service\app\settings.py src\services\ingestion_service\app\routers\uploads.py src\services\ingestion_service\app\services\upload_validation.py scripts\security_control_coverage_guard.py tests\unit\services\ingestion_service\test_settings.py tests\unit\services\ingestion_service\test_adapter_mode.py tests\unit\services\ingestion_service\services\test_upload_validation.py tests\integration\services\ingestion_service\test_ingestion_routers.py
python -m ruff format --check src\services\ingestion_service\app\settings.py src\services\ingestion_service\app\routers\uploads.py src\services\ingestion_service\app\services\upload_validation.py scripts\security_control_coverage_guard.py tests\unit\services\ingestion_service\test_settings.py tests\unit\services\ingestion_service\test_adapter_mode.py tests\unit\services\ingestion_service\services\test_upload_validation.py tests\integration\services\ingestion_service\test_ingestion_routers.py
make quality-wiki-docs-gate
make security-control-coverage-guard
$env:PYTHONPATH = "src/services/ingestion_service;src/libs/portfolio-common"; python -c "import app.main; print('ingestion app import ok')"
git diff --check
```

Results: 35 focused upload/settings/OpenAPI tests passed; scoped Ruff check and format check
passed; `make quality-wiki-docs-gate`, `make security-control-coverage-guard`, ingestion app
import proof, and `git diff --check` passed. `git diff --check` reported expected CRLF
normalization warnings only.

## Documentation Decision

Repo-local context, the upload boundary standard, operations runbook, security docs, security wiki,
ingestion wiki, and codebase review ledger were updated because upload parser resource budgets are
now part of the supported adapter-mode contract. No platform-wide skill update is required for this
slice; the same-pattern lesson is pinned in repo-local context and the upload boundary standard.
