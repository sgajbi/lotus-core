# CR-1319 Ingestion Service Framework Boundary

## Scope

Issue cluster: GitHub issue #624.

This slice removes FastAPI exception and dependency-provider coupling from ingestion business
services and adapter-mode policy.

## Objective

Make ingestion service construction and adapter-mode policy framework-neutral while preserving the
existing API behavior and downstream contracts. Routers and dependency adapters remain responsible
for HTTP mapping.

## Changes

1. Replaced adapter-mode `HTTPException` raises with framework-independent
   `AdapterModeDisabledError`.
2. Moved `require_upload_adapter_enabled(...)`,
   `require_portfolio_bundle_adapter_enabled(...)`, `get_ingestion_service(...)`, and
   `get_reference_data_ingestion_service(...)` into `app/dependencies.py`.
3. Removed FastAPI imports and dependency providers from `IngestionService` and
   `ReferenceDataIngestionService`.
4. Rewired ingestion routers and event replay dependency composition to import providers from
   `app/dependencies.py`.
5. Added pure adapter-mode policy tests, dependency HTTP-mapping tests, and a static guard for
   ingestion service framework coupling.
6. Added `docs/standards/ingestion-service-framework-boundary-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, Kafka key, Kafka header,
event payload, database schema, metric name, rate-limit behavior, upload-size behavior, or runtime
topology changed.

Adapter-mode-disabled API calls still map to HTTP `410 Gone` with the same machine-readable detail
shape: `code`, `capability`, and `message`.

## Validation Evidence

Focused local validation:

1. `python scripts/ingestion_service_framework_guard.py`
2. `python -m pytest tests/unit/services/ingestion_service/test_adapter_mode.py tests/unit/services/ingestion_service/test_dependencies.py tests/unit/scripts/test_ingestion_service_framework_guard.py -q`
3. `python -m pytest tests/unit/services/ingestion_service/test_adapter_mode.py tests/unit/services/ingestion_service/test_dependencies.py tests/unit/scripts/test_ingestion_service_framework_guard.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/unit/services/ingestion_service/routers/test_uploads.py tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py -q`
4. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "upload or reference_data" -q`
5. `python -m ruff check <touched Python paths>`
6. `python -m ruff format --check <touched Python paths>`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal dependency composition and does not
change operator-facing commands, public API behavior, supported features, or published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already covers replacing repeated framework/infrastructure coupling with ports, adapters,
guards, tests, and repo context.

## Remaining Work

GitHub issue #624 is locally fixed for the named FastAPI service-coupling acceptance criteria
pending PR CI/QA and issue closure.

Broader migration from legacy `app/services` modules into `app/application` use-case packages
remains incremental issue scope and must preserve public contracts slice by slice.
