# CR-613: Valuation Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The position valuation calculator and shared valuation-price helper each carried private
`Decimal(str(...))` normalization paths for required valuation inputs. That duplicated numeric
conversion behavior across a calculation hot path used by valuation and reconciliation support.

## Change

Added shared `portfolio_common.decimal_amounts` helpers for nullable and required Decimal
normalization, routed valuation unit-price logic and position valuation required numeric inputs
through those helpers, and kept required blank inputs on an explicit validation error path.

## Impact

This improves reuse and consistency across valuation calculations while preserving existing
positive market-price and FX-rate validation behavior, bond quote normalization, and valuation
response semantics. API route shape, response fields, OpenAPI contracts, database schema, wiki
source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_decimal_amounts.py tests/unit/libs/portfolio-common/test_valuation_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
