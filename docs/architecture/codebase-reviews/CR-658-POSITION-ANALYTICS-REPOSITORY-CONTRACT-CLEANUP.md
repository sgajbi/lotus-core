# CR-658: Position Analytics Repository Contract Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService.get_position_timeseries(...)` still guarded active repository methods
with optional `hasattr(...)` checks. Those checks let test doubles and fallback-style callers skip
snapshot-epoch resolution, position cashflow reads, portfolio cashflow context, or latest-before
continuity reads even though the production repository exposes those methods.

## Change

Made the position analytics input path use the concrete repository contract directly:

1. snapshot epoch resolution always uses `get_position_snapshot_epoch(...)` when the page token does
   not already carry a snapshot epoch,
2. position cashflows are loaded whenever requested rows and `include_cash_flows=True` are present,
3. portfolio cashflow context is loaded for non-empty returned pages,
4. latest-before rows are loaded for non-empty returned pages to preserve beginning-value
   continuity.

Updated analytics-timeseries service tests so their doubles provide the same active repository
dependencies used in production.

## Impact

This removes stale compatibility branching and prevents source-data products from silently dropping
cashflow context or continuity repair when a non-production double omits repository methods. API
response shape, page-token semantics, FX behavior, and database schema are unchanged.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
