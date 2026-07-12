# CR-618: Cost Basis Lot Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The cost-basis lot strategies and disposition engine still converted buy-lot quantity/cost fields
and sell quantities with local `Decimal(str(...))` calls. These are core calculation paths for
FIFO/AVCO lot state and sell-disposal cost basis, so duplicated coercion increases the chance of
inconsistent validation behavior across the cost engine.

## Change

Routed buy-lot quantity, base cost, local cost, and disposition sell quantity normalization through
`portfolio_common.decimal_amounts.required_decimal(...)`. Added focused coverage proving dirty
string-like values are normalized once before lot mutation or disposition delegation.

## Impact

This aligns FIFO, AVCO, and disposition quantity normalization with the shared portfolio-common
decimal helper while preserving existing positive quantity, non-negative cost basis, oversell, and
zero-state behavior. API route shape, response fields, OpenAPI contracts, database schema, wiki
source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_disposition_engine.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
