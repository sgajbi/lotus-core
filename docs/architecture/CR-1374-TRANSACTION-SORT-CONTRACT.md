# CR-1374 Transaction Sort Contract

## Objective

Fix GitHub issue #525 by making transaction-ledger sorting a typed, fail-fast API contract instead
of silently falling back to default ordering when callers submit unsupported sort fields or
directions.

## Changes

- Added a shared transaction sort policy in `query_service.app.application.transaction_sorting`.
- Validated `sort_by` and `sort_order` in the query-service dependency and returned a structured
  HTTP 400 detail for invalid values.
- Published allowed sort values in OpenAPI schema metadata while preserving the existing default
  route behavior when sort parameters are omitted.
- Reused the same sort policy in `TransactionRepository` so direct service/repository callers also
  fail fast instead of bypassing HTTP validation.
- Preserved deterministic ordering by keeping `transactions.id` as the tie-breaker for every
  supported sort field and direction.

## Expected Improvement

- Pagination becomes more auditable because unsupported caller sort intent cannot be hidden behind
  default ordering.
- API consumers can discover allowed values from OpenAPI instead of relying on prose.
- Runtime correctness improves because invalid sort requests stop before SQL execution.
- Design-time complexity decreases by moving sort vocabulary and validation into one shared policy.

## Tests Added

- Dependency tests reject invalid `sort_by` and `sort_order` with structured 400 detail.
- Repository tests reject invalid sort field/order before database execution.
- Repository tests prove settlement-date sorting uses a stable transaction-id tie-breaker.
- Router tests prove invalid sort query parameters return 400 and do not call the service.
- OpenAPI tests prove `sort_by` and `sort_order` expose allowed enum values and tie-breaker
  documentation.

## Validation Evidence

```powershell
python -m pytest tests/unit/services/query_service/test_dependencies.py tests/unit/services/query_service/repositories/test_transaction_repository.py::test_get_transactions_default_sort tests/unit/services/query_service/repositories/test_transaction_repository.py::test_get_transactions_custom_sort tests/unit/services/query_service/repositories/test_transaction_repository.py::test_get_transactions_invalid_sort_field_fails_fast tests/unit/services/query_service/repositories/test_transaction_repository.py::test_get_transactions_invalid_sort_order_fails_fast tests/unit/services/query_service/repositories/test_transaction_repository.py::test_get_transactions_settlement_date_sort_uses_stable_tie_breaker tests/integration/services/query_service/test_transactions_router.py::test_get_transactions_success_with_sorting_and_filters tests/integration/services/query_service/test_transactions_router.py::test_get_transactions_rejects_invalid_sort_field tests/integration/services/query_service/test_transactions_router.py::test_get_transactions_rejects_invalid_sort_order tests/integration/services/query_service/test_main_app.py::test_openapi_exposes_transaction_sort_enums -q
python -m ruff check src/services/query_service/app/application/transaction_sorting.py src/services/query_service/app/dependencies.py src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/test_dependencies.py tests/unit/services/query_service/repositories/test_transaction_repository.py tests/integration/services/query_service/test_transactions_router.py tests/integration/services/query_service/test_main_app.py
```

Final API, architecture, docs, typecheck, and diff checks are recorded in the issue comment before
commit.

## Downstream Compatibility Impact

Intentional behavior change: unsupported `sort_by`, empty `sort_by`, unsupported `sort_order`, and
empty `sort_order` now return HTTP 400 for the transaction ledger route instead of silently using
transaction-date descending behavior. Omitted parameters remain compatible and still default to
`transaction_date` descending. Valid `asc`/`desc` ordering, route path, response DTO, database
schema, pagination fields, source-data metadata, and runtime topology are unchanged.

## Same-Pattern Scan

The scan found caller-controlled `sort_by` / `sort_order` silent fallback only on the strategic
transaction ledger route. Other source-data products use fixed sort keys or page-token sort
metadata, not free-form HTTP sort parameters. Future endpoints with caller-controlled sorting must
define allowed values in one policy, publish them in OpenAPI, reject invalid values, and preserve a
deterministic tie-breaker.

## Docs, Context, And Skill Decision

- Codebase review ledger updated with #525 closure evidence.
- Repository context updated with the no-silent-sort-fallback rule.
- API governance docs updated to require documented allowed values and deterministic tie-breakers.
- No wiki update is required because public API navigation did not change and OpenAPI remains the
  consumer-facing contract for query parameter values.
- No platform skill update is required: existing issue-fix and backend delivery skills already
  require same-pattern scans and durable repo context updates.
