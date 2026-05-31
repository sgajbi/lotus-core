# CR-606: Holdings Weight Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Holdings weight calculation in `PositionService` still converted market value or cost basis inline
after query-service amount normalization was centralized. That left HoldingsAsOf weighting on a
separate conversion path from the related cashflow, liquidity, reporting, and transaction-cost
source-data products.

## Change

Added a small `_weight_base_value(...)` helper that routes holdings weight inputs through
`decimal_or_zero(...)` and keeps the existing market-value-first, cost-basis-fallback behavior
explicit and directly tested.

## Impact

This keeps numeric normalization consistent for HoldingsAsOf weight calculations while preserving
existing fallback valuation behavior and response shape. API route shape, response fields, OpenAPI
contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_position_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
