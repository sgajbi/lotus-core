# CR-699: Liquidity Ladder Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioLiquidityLadderService.get_liquidity_ladder(...)` resolved portfolio metadata before
reading the latest business date whenever callers omitted `as_of_date`. The method already
parallelizes snapshot, booked cashflow, and projected settlement evidence reads, but scope setup
remained serialized.

## Change

Default-date liquidity-ladder requests now resolve portfolio metadata and the latest business date
with `asyncio.gather(...)`. Explicit `as_of_date` requests continue to skip the
latest-business-date lookup and use the caller-provided date.

Added focused coverage proving portfolio and default-date reads start concurrently, and that
explicit-date requests do not call the default-date lookup.

## Impact

This reduces `PortfolioLiquidityLadder` latency for default-date liquidity evidence requests while
preserving portfolio validation, no-business-date failure behavior, horizon validation,
snapshot/cashflow evidence concurrency, booked-only projected-read suppression, cash bucket
calculation, response shape, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused liquidity-ladder service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
