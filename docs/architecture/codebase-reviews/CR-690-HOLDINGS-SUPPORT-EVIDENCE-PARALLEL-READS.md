# CR-690: Holdings Support Evidence Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PositionService.get_portfolio_positions(...)` built holdings rows and then read held-since evidence
before reading latest market-price freshness evidence. Those support reads are independent once the
response positions and response as-of date are known, so holdings responses with current-epoch
positions serialized two database reads on the hot path.

## Change

Computed the response as-of date and market-price freshness security set before support evidence
reads. When held-since evidence is needed, the service now reads held-since dates and latest
market-price dates with `asyncio.gather(...)`; when no held-since read is needed, it preserves the
single market-price freshness read.

Added focused coverage proving held-since and latest market-price freshness reads start
concurrently.

## Impact

This reduces `HoldingsAsOf` latency for populated portfolios while preserving snapshot/history
merge semantics, fallback valuation behavior, held-since defaults, market-price freshness quality
classification, response shape, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused position-service holdings proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
