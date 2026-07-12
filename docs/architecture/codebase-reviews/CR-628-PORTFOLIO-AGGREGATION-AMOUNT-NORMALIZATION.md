# CR-628: Portfolio Aggregation Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Portfolio-timeseries aggregation had already been hardened for currency normalization and FX-rate
reuse, but the summed position-timeseries amount fields still used raw `value or Decimal(0)`
fallbacks. That left aggregation arithmetic on a different numeric normalization policy from the
timeseries generator, reconciliation, valuation, query-service analytics, and source-data product
paths.

Sparse generated position-timeseries evidence such as blank numeric text or null amount fields could
therefore fail or behave differently from adjacent calculation flows.

## Change

Added `portfolio_common.decimal_amounts.decimal_or_zero(...)` for shared zero-default amount
normalization, then routed position-timeseries market values, portfolio cashflows, and fee amounts
through it before applying FX conversion and summing.

Added focused portfolio-common helper coverage and portfolio-aggregation logic coverage for blank,
null, invalid, and padded numeric amount evidence.

## Impact

This keeps portfolio-timeseries aggregation deterministic for performance input generation,
reconciliation support, reprocessing, and downstream query/gateway consumers while preserving output
shape, FX lookup/caching behavior, and missing/non-positive FX failure semantics.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal calculation-path hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/services/portfolio_aggregation_service/core/test_portfolio_aggregation_timeseries_logic.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
