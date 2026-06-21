# CR-1148 Business-Date Ingestion Route Boundary

Date: 2026-06-22

## Scope

Business-date ingestion route orchestration in
`src/services/ingestion_service/app/routers/business_dates.py`.

## Finding

`ingest_business_dates(...)` mixed write-mode enforcement, write-rate limiting, empty payload
validation, future-date policy checks, optional monotonic-advance checks, idempotent job creation,
duplicate ACK handling, publish failure bookkeeping, post-publish queue bookkeeping, and final ACK
assembly in one C-ranked API route.

Radon reported:

- `ingest_business_dates`: `C (17)`

## Action Taken

Extracted focused helpers for:

- ingestion write-mode enforcement,
- business-date write-rate limiting,
- payload/future-date/monotonic policy validation,
- idempotent job creation,
- publish failure handling,
- queue bookkeeping,
- business-date ACK assembly.

The route path, request/response contract, canonical error bodies, idempotency behavior, future-date
policy, monotonic policy, publish failure body, failed record-key reporting, and post-publish
bookkeeping behavior remain unchanged.

## Evidence

Focused route proof:

- `python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_rejects_empty_payload_with_canonical_error tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_rejects_monotonic_regression tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_returns_failed_record_keys_when_publish_fails -q`
- Result: `7 passed`

Focused static proof:

- `python -m ruff check src/services/ingestion_service/app/routers/business_dates.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/ingestion_service/app/routers/business_dates.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/ingestion_service/app/routers/business_dates.py -s --exclude "*/build/*"`
- Result: `ingest_business_dates` is `A (2)`

Measured movement:

- `ingest_business_dates`: `C (17)` -> `A (2)`

## Residual Risk

This slice does not change business-date methodology, calendar persistence, Kafka publication,
idempotency semantics, or route/OpenAPI contracts. `_enforce_business_date_monotonic_advance(...)`
is B-ranked and can be reviewed separately if policy logic grows.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of calendar ingestion controls,
- separation of validation policy from publication side effects,
- focused proof across success, duplicate idempotency, empty payload, mode block, rate limit,
  monotonic regression, and publish failure paths.

It does not claim full bank-buyable readiness for `lotus-core`.
