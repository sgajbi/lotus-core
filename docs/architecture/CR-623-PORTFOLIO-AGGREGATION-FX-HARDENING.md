# CR-623: Portfolio Aggregation FX Hardening

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`portfolio_aggregation_service` still used the older portfolio-timeseries aggregation path for
currency handling. It compared raw currency text, used `Decimal(1.0)`, fetched FX rates repeatedly
for repeated instrument/date rows, and accepted repository FX values without the shared positive-rate
guard used by the newer timeseries generator.

## Change

Aligned portfolio aggregation with the hardened timeseries-generator calculation shape:

1. normalize portfolio and instrument currency codes before comparison,
2. deduplicate instrument lookup keys before repository fetch,
3. cache FX rates by `(instrument_currency, portfolio_currency, valuation_date)`,
4. route repository FX values through `coerce_positive_fx_rate_or_none(...)`,
5. fail closed on missing or non-positive FX evidence.

Added direct unit coverage for same-currency normalization without FX lookup, FX cache reuse for
repeated rows, and non-positive FX rejection.

## Impact

This reduces repeated reference-data lookups and closes a stale calculation path in portfolio
timeseries aggregation while preserving the existing aggregate output shape and missing-FX failure
contract.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal calculation-path hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/portfolio_aggregation_service/core/test_portfolio_timeseries_logic.py tests/unit/services/portfolio_aggregation_service/consumers/test_portfolio_timeseries_consumer.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
