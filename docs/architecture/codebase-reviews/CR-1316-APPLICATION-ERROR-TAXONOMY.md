# CR-1316 Application Error Taxonomy

## Scope

Issue cluster: GitHub issue #643.

This slice introduces a framework-independent application error taxonomy for the representative
ingestion upload workflow.

## Objective

Stop coupling application validation failures to FastAPI `HTTPException` and HTTP status constants.
Keep the existing upload API error contract unchanged while making application use-case execution
testable without FastAPI.

## Changes

1. Added `src/services/ingestion_service/app/application/errors.py`.
2. Added `ApplicationError`, `ValidationRejected`, and `UnsupportedOperation`.
3. Routed `UploadIngestionService` unsupported-format, invalid-content, empty-upload,
   partial-rejection, and no-valid-row failures through application errors.
4. Moved `get_upload_ingestion_service(...)` dependency wiring into
   `src/services/ingestion_service/app/routers/uploads.py`.
5. Added `upload_application_error_to_http(...)` in the upload router to preserve existing HTTP
   400 and 422 mappings.
6. Added service-level tests proving non-HTTP application errors.
7. Added router-level tests proving HTTP mapping and response-detail compatibility.
8. Added `scripts/application_error_taxonomy_guard.py` and wired it into
   `make architecture-guard`.
9. Added `docs/standards/application-error-taxonomy-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, upload parsing behavior, row-validation
behavior, publish behavior, Kafka topic, database schema, or runtime topology changed.

Existing API clients receive the same HTTP status classes and `detail` bodies for the migrated
upload validation paths.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py tests/unit/services/ingestion_service/routers/test_uploads.py tests/unit/scripts/test_application_error_taxonomy_guard.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "upload_preview_rejects_unsupported_file_format or upload_commit_rejects_unsupported_file_format or upload_commit_xlsx_rejects_invalid_without_partial or upload_commit_rejects_empty_csv" -q`
3. `python scripts/application_error_taxonomy_guard.py`
4. Scoped Ruff check and format-check for the touched Python modules.
5. `make architecture-guard`
6. `python scripts/wiki_validation_guard.py`
7. `git diff --check`

The focused unit command passed locally with 10 tests. The upload integration compatibility subset
passed locally with 4 tests and 218 deselected.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, codebase review ledger, and repo context.

No wiki update is required because this slice changes an internal application/API error boundary,
not operator-facing commands, route behavior, supported features, or published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already directs repeated framework/infrastructure coupling issues toward application
boundaries, tests, guards, and context updates.

## Remaining Work

GitHub issue #643 is locally fixed for representative application-error acceptance pending PR CI/QA
and issue closure.

Other application services may still use transport-specific errors as transitional scope; future
slices should migrate them only when the same application/API boundary risk is present and covered
by focused tests.
