# CR-656: Analytics Position Paging Fallback Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService._portfolio_observation_rows(...)` still carried a compatibility branch
for repositories that could not list position observation dates or resolve latest prior EOD rows.
That stale branch could load the full position-timeseries window before date pagination, weakening
the bounded-read posture introduced for portfolio analytics input generation.

## Change

Removed the compatibility branch and made portfolio analytics assembly use the active repository
contract directly:

1. resolve observed position dates first,
2. page by observation date,
3. load only the selected page-date position rows,
4. resolve prior EOD continuity through the latest-before repository helper.

Updated analytics-timeseries service tests so their doubles model the active repository contract
instead of the retired full-window fallback.

## Impact

This keeps `PortfolioTimeseriesInput` reads aligned to the bounded page-date query shape used in
production. It reduces stale service branching without changing API response shape, pagination
tokens, snapshot epoch semantics, FX handling, cashflow handling, or database schema.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
