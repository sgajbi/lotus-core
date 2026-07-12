# CR-657: Portfolio Analytics Direct Row Fallback Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService.get_portfolio_timeseries(...)` still carried a legacy fallback that read
direct `portfolio_timeseries` rows when position-derived portfolio assembly helpers were absent.
Production already uses the position-derived path so portfolio analytics inputs can preserve
day-boundary capital continuity, cashflow semantics, snapshot epoch filtering, and page-date bounded
position reads. The fallback kept unused repository methods alive and made tests exercise a
non-production query shape.

## Change

Removed the direct `portfolio_timeseries` fallback from portfolio analytics input assembly and
deleted the unused repository helpers:

1. `list_portfolio_timeseries_rows(...)`,
2. `list_portfolio_observation_dates(...)`,
3. `get_portfolio_snapshot_epoch(...)`.

Updated analytics-timeseries service and repository tests to prove the active position-derived
contract instead of the retired direct-row fallback.

## Impact

This reduces stale query-service surface area and keeps `PortfolioTimeseriesInput` behavior tied to
the bounded, position-derived production path. API response shape, page-token semantics,
performance-end-date resolution, cashflow handling, FX behavior, and database schema are unchanged.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
