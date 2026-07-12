# CR-669: Liquidity Ladder Parallel Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioLiquidityLadderService.get_liquidity_ladder(...)` resolved the portfolio, business date,
and latest snapshot rows, then read booked cashflow evidence and projected settlement evidence
sequentially for projected ladder windows. Those two cashflow evidence reads are independent after
the ladder date range is known.

## Change

For `include_projected=True`, the service now reads booked cashflow evidence and projected
settlement evidence with `asyncio.gather(...)`. The booked-only path remains a single booked
cashflow read and still skips projected settlement evidence.

Added service coverage that would deadlock under sequential execution, proving the projected ladder
path starts both reads concurrently.

## Impact

This reduces liquidity ladder latency for projected windows without changing route shape, response
contracts, database schema, source-data product metadata, source-batch fingerprints, wiki source, or
platform contracts.

## Validation

Local validation passed:

1. focused liquidity ladder service proof
2. focused cashflow repository query-shape proof
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
