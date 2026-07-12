# CR-603: Reporting Amount Normalization Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cash movement, cash balance, and reporting services still carried inline
`Decimal(str(... or 0))` conversion after the shared query-service amount helper was introduced.
Those paths build cash-movement buckets, cash-account balances, AUM totals, portfolio summaries, and
allocation source rows from high-use snapshot and cashflow evidence.

## Change

Routed those read-path amount conversions through the shared `decimal_or_zero(...)` helper while
preserving existing total, movement-direction, FX conversion, and allocation behavior.

## Impact

This extends shared amount normalization across the main query-service reporting surfaces and avoids
drift in null/blank/Decimal handling. API route shape, response fields, OpenAPI contracts, database
schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_cash_movement_service.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
