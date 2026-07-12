# CR-675: Portfolio Analytics Page Support Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService._portfolio_observation_rows(...)` first reads the page's position rows,
then needs support evidence for the same page: position-to-portfolio FX maps,
portfolio-to-reporting FX maps, portfolio cash flows, position cash flows, and previous-position
rows for continuity. After page dates and normalized security IDs are known, those support reads are
independent, but the service loaded them sequentially.

## Change

The service now resolves the page support inputs with one `asyncio.gather(...)` call after the
position rows are loaded. It also computes normalized security IDs once and reuses that list for
both position cash-flow and previous-row reads.

Added service coverage that would deadlock under sequential execution, proving page support reads
are started concurrently.

## Impact

This reduces `PortfolioTimeseriesInput:v1` latency for populated analytics pages while preserving
date paging, continuity repair, cash-flow classification, FX validation, response contracts,
database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused analytics time-series service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
