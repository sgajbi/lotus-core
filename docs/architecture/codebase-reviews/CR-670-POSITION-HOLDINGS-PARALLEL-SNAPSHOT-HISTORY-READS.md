# CR-670: Position Holdings Parallel Snapshot History Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PositionService.get_portfolio_positions(...)` reads latest snapshot rows and latest position
history fallback rows sequentially after portfolio and effective-date resolution. The two repository
reads are independent and are merged later by normalized security ID so missing snapshot rows can be
supplemented from history.

## Change

The service now reads the snapshot and history row sets with `asyncio.gather(...)` for both
date-scoped and projected/latest holdings paths. The downstream merge, valuation fallback,
held-since lookup, market-price freshness check, evidence timestamp, and response shape are
unchanged.

Added service coverage that would deadlock under sequential execution, proving the snapshot and
history reads are started concurrently.

## Impact

This reduces holdings API latency for portfolios that require both snapshot and history fallback
evidence without changing route shape, response contracts, database schema, source-data product
metadata, wiki source, or platform contracts.

## Validation

Local validation passed:

1. focused position service proof
2. focused position repository query-shape proof
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
