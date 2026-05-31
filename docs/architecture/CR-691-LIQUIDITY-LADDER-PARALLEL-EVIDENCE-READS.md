# CR-691: Liquidity Ladder Parallel Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioLiquidityLadderService.get_liquidity_ladder(...)` loaded latest snapshot rows before
reading booked and projected cashflow evidence. After portfolio and business-date resolution, those
snapshot and cashflow evidence reads are independent, so liquidity ladder assembly serialized
database work on the source-data evidence hot path.

## Change

Prepared the snapshot-row read and booked cashflow read together after resolving the portfolio and
as-of date. For projected ladders, the service now resolves snapshot rows, booked cashflows, and
projected settlement cashflows in one `asyncio.gather(...)`; booked-only ladders resolve snapshot
rows and booked cashflows together while still skipping the projected read.

Added focused coverage proving snapshot, booked cashflow, and projected cashflow reads start
concurrently.

## Impact

This reduces `PortfolioLiquidityLadder` latency for populated portfolios while preserving portfolio
validation, business-date failure behavior, booked-only behavior, cash/non-cash partitioning,
liquidity-tier exposure, bucket calculations, source-data runtime metadata, response shape,
database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused liquidity-ladder service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
