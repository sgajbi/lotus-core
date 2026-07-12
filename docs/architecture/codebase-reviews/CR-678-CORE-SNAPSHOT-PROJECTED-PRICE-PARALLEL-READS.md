# CR-678: Core Snapshot Projected Price Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CoreSnapshotService._resolve_projected_positions(...)` repriced projected securities that had no
usable baseline market value by loading market prices inside the projected-position loop. For
multi-security simulation snapshots, those price reads are independent once quantity effects and
missing instrument enrichment are resolved.

## Change

The service now collects all projected securities that require fresh pricing, reads their latest
market prices with `asyncio.gather(...)`, validates missing or blank price evidence with the
existing error behavior, and then resolves market-to-portfolio FX once per normalized market
currency before applying projected values.

Added service coverage that would deadlock under sequential execution, proving projected security
price reads are started concurrently.

## Impact

This reduces simulated core snapshot latency for multi-security projected portfolios while
preserving snapshot preference, instrument enrichment, missing-price and missing-FX failure
behavior, market-currency FX reuse, response contracts, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused core snapshot service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
