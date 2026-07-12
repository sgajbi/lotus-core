# CR-698: Holdings Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PositionService.get_portfolio_positions(...)` validated portfolio existence before reading the
latest business date for default-date, non-projected holdings requests. The method already
parallelizes snapshot/history and support-evidence reads, but scope setup remained serialized.

## Change

Default-date, non-projected holdings requests now resolve portfolio existence and the latest
business date with `asyncio.gather(...)`. Explicit `as_of_date` requests and projected holdings
requests continue to skip the latest-business-date lookup.

Added focused coverage proving portfolio-existence and default-date reads start concurrently, and
that explicit-date requests do not call the default-date lookup.

## Impact

This reduces `HoldingsAsOf` latency for default-date holdings requests while preserving portfolio
validation, projected-holdings behavior, explicit-date behavior, snapshot/history merge semantics,
fallback valuation continuity, held-since evidence, market-price freshness evidence, response
shape, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused position-service holdings proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
