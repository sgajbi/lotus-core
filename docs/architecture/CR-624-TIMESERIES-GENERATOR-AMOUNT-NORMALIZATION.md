# CR-624: Timeseries Generator Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The timeseries generator still mixed direct `Decimal(...)` conversion with raw `or Decimal(0)`
fallbacks for snapshot, cashflow, and position-timeseries amount fields. Those calculation paths
feed downstream portfolio aggregation, reconciliation, performance inputs, and reprocessing
supportability.

## Change

Added small local zero-default helpers backed by `portfolio_common.decimal_amounts.decimal_or_none`
in the position and portfolio timeseries generator logic. The generator now normalizes:

1. previous/current snapshot market value, quantity, and local cost fields,
2. cashflow amounts before position-flow normalization, portfolio-flow accumulation, and fee
   extraction,
3. position-timeseries market value, portfolio cashflow, and fee fields before portfolio
   aggregation.

Focused tests cover string and blank amount seams for both daily position-timeseries generation and
portfolio-timeseries aggregation.

## Impact

This keeps timeseries calculation semantics aligned with the shared decimal normalization used by
valuation, reconciliation, cost, simulation, and query-service read paths while preserving output
shape, sign handling, fee extraction, and FX behavior.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal calculation-path hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_portfolio_timeseries_logic.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
