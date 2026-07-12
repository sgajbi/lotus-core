# CR-1381 Business-Date Ingestion Command Boundary

## Objective

Complete GitHub issue #533 by moving business-date ingestion lifecycle orchestration out of the
HTTP router and into an application command handler while preserving the public API contract.

## Expected Improvement

- The business-date router is now a thin HTTP adapter that resolves idempotency metadata, invokes a
  command handler, maps typed command errors, and builds the existing ACK response.
- `BusinessDateIngestionCommandHandler` owns write-mode checks, rate limits, policy validation,
  ingestion job create/replay, publish failure marking, and accepted-to-queued bookkeeping.
- `BusinessDateIngestionPolicy` remains the focused policy boundary for empty payload, max future
  date, and monotonic calendar advancement rules.
- Focused tests cover the command handler without FastAPI, reducing design-time coupling and making
  lifecycle behavior easier to validate.

## Changes

- Added `src/services/ingestion_service/app/services/business_date_ingestion_commands.py`.
- Added dependency wiring through `get_business_date_ingestion_command_handler(...)`.
- Slimmed `src/services/ingestion_service/app/routers/business_dates.py` to command invocation and
  HTTP error mapping.
- Added application unit tests for success, idempotency replay, publish failure marking,
  bookkeeping failure evidence, and mode-denial mapping.
- Updated the existing business-date route test to patch the application command boundary for rate
  limiting.

## Compatibility

No route path, OpenAPI response metadata, success DTO, Kafka topic, database schema, metric, or
downstream contract changed. Failure codes remain stable:

- `INGESTION_MODE_BLOCKS_WRITES`
- `INGESTION_RATE_LIMIT_EXCEEDED`
- `BUSINESS_DATE_PAYLOAD_EMPTY`
- `BUSINESS_DATE_FUTURE_POLICY_VIOLATION`
- `BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION`
- `INGESTION_PUBLISH_FAILED`
- `INGESTION_JOB_BOOKKEEPING_FAILED`

This is a design-modularity improvement inside the existing ingestion service deployable; no
runtime split is justified.

## Validation

Focused validation for this slice:

- `python -m pytest tests/unit/services/ingestion_service/application/test_business_date_ingestion_commands.py tests/unit/services/ingestion_service/services/test_business_date_ingestion_policy.py -q`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_endpoint tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_replays_duplicate_idempotency_key tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_rejects_empty_payload_with_canonical_error tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_returns_503_when_mode_blocks_writes tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_returns_429_when_rate_limited tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_rejects_monotonic_regression tests/integration/services/ingestion_service/test_ingestion_routers.py::test_ingest_business_dates_returns_failed_record_keys_when_publish_fails -q`
- scoped Ruff lint and format checks for touched source/test files.
- Radon complexity/maintainability on the router and new command handler.

## Documentation And Wiki Decision

Updated this architecture note, the codebase review ledger, and repo-local engineering context. No
README or wiki source update is needed because the public operator command and API contract did not
change.

## Follow-Up

Issue #533 remains pending PR CI/QA, merge to `main`, and post-merge closure. Adjacent ingestion
routes still contain command orchestration and should be extracted under their own issue-backed
slices rather than folded into this business-date boundary change.
