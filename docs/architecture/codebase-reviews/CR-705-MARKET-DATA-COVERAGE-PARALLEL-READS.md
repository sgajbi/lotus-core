# CR-705: Market Data Coverage Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`get_market_data_coverage(...)` read latest market prices before starting latest FX-rate reads even
though the price and FX scopes are both derived directly from the request. That made the market data
coverage source product pay avoidable sequential latency across two independent reference-data
evidence reads.

## Change

Moved price and FX lookup scope derivation ahead of the repository calls and routed
`list_latest_market_prices(...)` and `list_latest_fx_rates(...)` through one `asyncio.gather(...)`
phase. Existing request-scope deduplication, normalization, stale/missing classification, runtime
metadata, and response shape remain unchanged.

Added focused integration-service coverage that proves latest price and latest FX reads start
concurrently.

## Impact

This reduces `MarketDataCoverageWindow` latency for requests that include both instrument prices and
currency pairs while preserving coverage classification, source-data product evidence semantics,
response contracts, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused integration-service market-data coverage proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
