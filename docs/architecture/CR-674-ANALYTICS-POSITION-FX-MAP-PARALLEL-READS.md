# CR-674: Analytics Position FX Map Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService._get_position_to_portfolio_rate_maps(...)` normalized and deduplicated
position currencies, but then loaded each distinct non-portfolio currency FX map sequentially. For
multi-currency private-bank portfolios this serialized independent FX map reads over the same
analytics window before portfolio and position time-series rows could be assembled.

## Change

The service now starts one FX map read per distinct non-portfolio position currency and awaits those
reads with `asyncio.gather(...)`. Same-currency positions still resolve to an empty rate map without
repository access, and duplicate currency inputs are still collapsed before any query is issued.

Added service coverage that would deadlock under sequential execution, proving distinct currency FX
maps are requested concurrently.

## Impact

This reduces analytics time-series latency for multi-currency holdings while preserving
currency-normalization behavior, same-currency short-circuiting, response contracts, database
schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused analytics time-series service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
