# CR-1320 Bulk Upload Component Boundary

## Scope

Issue cluster: GitHub issue #625.

This slice splits bulk-upload parsing/validation from commit orchestration and publish dispatch.

## Objective

Make upload preview and validation testable without FastAPI, Kafka, database sessions, real
ingestion services, or downstream systems, while preserving existing upload API behavior and
publication semantics.

## Changes

1. Added `BulkUploadValidator` and `UploadValidationReport` in `upload_validation.py`.
2. Added `UploadRecordPublisher` as the upload publisher port.
3. Added `IngestionServiceUploadPublisher` as the adapter from validated upload records to the
   existing canonical ingestion publish methods.
4. Slimmed `UploadIngestionService` so it owns preview/commit policy and delegates validation and
   publication.
5. Updated router composition to construct `UploadIngestionService` with the validator and
   ingestion-service publisher adapter.
6. Added focused tests for validation, publisher dispatch, upload orchestration, and the static
   upload component boundary guard.
7. Added `docs/standards/bulk-upload-component-boundary-standard.md`.

## Behavior And Compatibility

No route path, form field, request DTO, response DTO, OpenAPI metadata, Kafka topic, Kafka key,
Kafka header, upload validation reason code, upload response message, upload sample-row behavior,
database schema, metric name, or runtime topology changed.

The existing upload entity DTOs still define row validation semantics. The split only changes
internal ownership of parsing, validation, commit policy, and publish dispatch.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/ingestion_service/services/test_upload_validation.py tests/unit/services/ingestion_service/services/test_upload_publishers.py tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py tests/unit/scripts/test_upload_component_boundary_guard.py -q`
2. `python scripts/upload_component_boundary_guard.py`
3. `python scripts/ingestion_service_framework_guard.py`
4. `python -m pytest tests/unit/services/ingestion_service/services/test_upload_validation.py tests/unit/services/ingestion_service/services/test_upload_publishers.py tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py tests/unit/scripts/test_upload_component_boundary_guard.py tests/unit/scripts/test_application_error_taxonomy_guard.py -q`
5. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k upload -q`
6. `python -m ruff check <touched Python paths>`
7. `python -m ruff format --check <touched Python paths>`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal component ownership and does not
change operator-facing commands, public API behavior, supported features, or published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already directs repeated concrete dependency coupling toward ports, adapters, tests,
guards, and repo context.

## Remaining Work

GitHub issue #625 is locally fixed for the pure parser/validator, publisher port, table-driven unit
tests, and integration/API translation acceptance criteria pending PR CI/QA and issue closure.

Broader upload DTO/domain separation remains future work and must be done with explicit API
contract proof because the current upload validation semantics are defined by existing ingestion
DTOs.
