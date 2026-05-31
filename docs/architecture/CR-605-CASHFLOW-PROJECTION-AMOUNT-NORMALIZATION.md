# CR-605: Cashflow Projection Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cashflow projection daily aggregation still converted row amounts inline with `Decimal(str(...))`
after query-service amount normalization was centralized. That left the operational cashflow
projection path on a separate null/blank handling behavior from liquidity ladder, reporting, cash
movement, and transaction-cost source-data products.

## Change

Routed `CashflowProjectionService._sum_by_date(...)` through `decimal_or_zero(...)` and added
coverage proving blank and null row amounts aggregate as zero instead of failing during daily
projection construction.

## Impact

This keeps cashflow projection amount normalization aligned with the rest of the query-service
calculation paths while preserving daily totals, cumulative cashflow, and projected/booked mode
behavior. API route shape, response fields, OpenAPI contracts, database schema, wiki source, and
platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_cashflow_projection_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
