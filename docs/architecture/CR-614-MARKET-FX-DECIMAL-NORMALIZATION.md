# CR-614: Market FX Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Shared market-price and FX-rate coercion helpers still carried their own Decimal conversion and
invalid-input handling after `portfolio_common.decimal_amounts` was introduced. These helpers sit
on valuation, reconciliation, and timeseries calculation paths, so duplicated coercion increases
drift risk in core calculation behavior.

## Change

Routed `coerce_positive_market_price_or_none(...)` and `coerce_positive_fx_rate_or_none(...)`
through `decimal_or_none(...)`, and extended the shared helper to return `None` for invalid numeric
text while preserving Decimal instances and blank/null semantics.

## Impact

This keeps positive price/rate normalization centralized while preserving the existing contract:
missing, invalid, zero, and negative values return `None`; positive numeric values return
`Decimal`. API route shape, response fields, OpenAPI contracts, database schema, wiki source, and
platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_decimal_amounts.py tests/unit/libs/portfolio-common/test_market_prices.py tests/unit/libs/portfolio-common/test_fx_rates.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
