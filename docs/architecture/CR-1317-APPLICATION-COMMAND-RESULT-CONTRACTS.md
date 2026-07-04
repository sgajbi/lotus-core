# CR-1317 Application Command And Result Contracts

## Scope

Issue cluster: GitHub issue #642.

This slice introduces representative application command/result contracts for one write workflow
and one read workflow.

## Objective

Remove legacy API DTO coupling from representative application services so API contract evolution,
worker usage, batch usage, and use-case behavior can be tested independently. Preserve existing API
responses and downstream behavior.

## Changes

1. Added `src/services/ingestion_service/app/application/upload_commands.py` with upload preview
   and commit command/result models.
2. Routed `UploadIngestionService.preview_upload(...)` and `commit_upload(...)` through application
   command/result contracts instead of upload API response DTOs.
3. Added router mapping helpers in `src/services/ingestion_service/app/routers/uploads.py` to
   translate API form/file inputs into commands and application results back to API response DTOs.
4. Added `src/services/query_service/app/application/lookup_catalog.py` with lookup query/result
   models.
5. Routed `LookupCatalogService` through lookup application query/result contracts instead of
   returning lookup API DTOs.
6. Added router mapping in `src/services/query_service/app/routers/lookups.py` to preserve public
   lookup response DTOs.
7. Added `src/services/query_service/app/application/core_snapshot.py` with a canonical core
   snapshot identity command.
8. Replaced core snapshot request fingerprinting from `request.model_dump(mode="json")` with the
   canonical identity command payload while preserving the payload shape.
9. Added `scripts/application_command_result_guard.py` and wired it into
   `make architecture-guard`.
10. Added `docs/standards/application-command-result-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, upload parsing behavior, row-validation
behavior, publish behavior, lookup filtering behavior, lookup sorting behavior, database schema,
Kafka topic, metric name, or runtime topology changed.

Existing API clients continue to receive the same upload and lookup response shapes. The migrated
application services no longer expose those API DTOs as their internal use-case contract.

Core snapshot request fingerprints keep the same canonical request payload shape while no longer
depending on API DTO serialization as the source of identity truth.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py tests/unit/services/ingestion_service/routers/test_uploads.py tests/unit/services/query_service/services/test_lookup_catalog_service.py tests/unit/services/query_service/routers/test_lookups_router.py tests/unit/services/query_service/services/test_core_snapshot_service.py tests/unit/scripts/test_application_command_result_guard.py -q`
2. `python scripts/application_command_result_guard.py`
3. Scoped Ruff check and format-check for the touched Python modules.
4. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "upload_preview_rejects_unsupported_file_format or upload_commit_rejects_unsupported_file_format or upload_commit_xlsx_rejects_invalid_without_partial or upload_commit_rejects_empty_csv or upload_preview_csv_with_aliases or upload_commit_csv_publishes_valid_rows" -q`
5. `python -m pytest tests/integration/services/query_service/test_lookup_contract_router.py -q`

The focused unit command passed locally with 57 tests. The upload integration subset passed locally
with 4 tests and 218 deselected. The lookup integration contract tests passed locally with 5 tests.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal application/API boundaries while
preserving public API behavior and operator-facing commands.

No platform skill source change is required in this slice because the existing backend delivery
guidance already directs repeated DTO/framework coupling issues toward application boundaries,
tests, guards, and context updates.

## Remaining Work

GitHub issue #642 is locally fixed for representative write, read/source-data, and canonical
request-fingerprint acceptance pending architecture guard proof, PR CI/QA, and issue closure.

Other services still contain API DTO usage as transitional backlog. Future slices should migrate
them when touched, especially portfolio bundle ingestion, reconciliation run orchestration, core
snapshot identity, and broader integration source-data workflows.
