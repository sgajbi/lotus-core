# CR-599: Transaction FX Conversion Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Transaction ledger reads and realized-tax summaries still carried a transaction-service-local FX
cache after cash balance and reporting paths moved to the shared query-service converter. The local
implementation duplicated currency normalization, identity conversion, missing-rate failure
behavior, and cache lookup semantics on a high-use ledger API path.

## Change

Routed `TransactionService` conversion wrappers through `CachedFxRateConverter` while preserving the
existing `_convert_amount(...)` and `_get_fx_rate(...)` method shape used by transaction reporting
currency fields and tax-summary aggregation.

## Impact

This keeps FX conversion behavior centralized across cash, reporting, and transaction query-service
read paths, reducing drift risk for normalized currency handling and missing-rate errors. API route
shape, response fields, OpenAPI contracts, database schema, wiki source, and platform contracts are
unchanged.

No wiki update was needed because this is internal service-boundary reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_fx_conversion.py tests/unit/services/query_service/services/test_transaction_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
