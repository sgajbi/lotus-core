# CR-706: Performance Horizon Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`_latest_available_performance_date(...)` read the latest portfolio-timeseries horizon before
starting the latest position-timeseries horizon read. Those date lookups are independent and feed
portfolio reference and analytics timeseries responses, so the analytics input surface paid
avoidable sequential latency before applying the existing conservative horizon bound.

## Change

Routed `get_latest_portfolio_timeseries_date(...)` and
`get_latest_position_timeseries_date(...)` through `asyncio.gather(...)` inside the shared helper.
The helper still incorporates observed page dates and still returns the minimum complete horizon
bounded by the requested as-of date.

Added focused analytics-timeseries service coverage that proves the two horizon reads start
concurrently.

## Impact

This reduces portfolio analytics reference and portfolio-timeseries horizon resolution latency
while preserving conservative performance-end-date semantics, observed-date handling, response
contracts, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused analytics-timeseries service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
