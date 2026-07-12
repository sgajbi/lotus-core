# CR-659: Analytics Performance Horizon Contract Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService._latest_available_performance_date(...)` still treated
`get_latest_position_timeseries_date(...)` as an optional repository method even though the
production analytics repository exposes it. That compatibility guard let partial test doubles hide
a missing production dependency and could make portfolio/reference performance horizons depend only
on portfolio-level rows when position-level analytics evidence had the authoritative lag boundary.

## Change

Removed the optional guard and made latest performance-horizon resolution call both active
repository methods directly:

1. `get_latest_portfolio_timeseries_date(...)`,
2. `get_latest_position_timeseries_date(...)`.

Updated analytics-timeseries service tests so repository doubles provide the production-equivalent
position-horizon method wherever portfolio/reference horizon resolution is exercised.

## Impact

This keeps `PortfolioTimeseriesInput` and `PortfolioAnalyticsReference` horizon metadata aligned to
the same concrete repository contract used in production. It reduces stale compatibility branching
without changing API response shape, page-token semantics, database schema, OpenAPI contracts, or
wiki source.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
