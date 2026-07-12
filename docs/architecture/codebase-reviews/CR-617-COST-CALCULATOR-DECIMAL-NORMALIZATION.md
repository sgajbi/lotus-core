# CR-617: Cost Calculator Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The cost calculator still normalized FX, dividend/interest price checks, and cash movement fallback
amounts with local `Decimal(str(...))` paths. The cash movement path also treated `None` and empty
strings as zero but did not treat whitespace-only gross amounts consistently, leaving a fragile
edge on cash deposit, withdrawal, and cash-sell calculation flows.

## Change

Routed cost-calculator decimal field normalization through
`portfolio_common.decimal_amounts.decimal_or_none(...)`, preserved the existing invalid decimal
error text for FX and price validation, and centralized cash movement fallback amount handling in a
local zero-default helper.

## Impact

This aligns cost-calculator amount normalization with the shared portfolio-common decimal helper
while preserving existing BUY, SELL, DIVIDEND, INTEREST, cash deposit, cash withdrawal, and cash
sell semantics. API route shape, response fields, OpenAPI contracts, database schema, wiki source,
and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
