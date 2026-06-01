# CR-676: Position Analytics Page Support Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`AnalyticsTimeseriesService.get_position_timeseries(...)` reads a bounded position page, then loads
support inputs for that same page: portfolio cash flows, optional position cash flows, FX maps, and
previous-position rows for continuity. Once page dates and normalized security IDs are known, those
support reads are independent, but the service loaded them sequentially.

## Change

The service now resolves the position page support inputs with `asyncio.gather(...)`, including
optional position cash-flow evidence when requested. Normalized security IDs are computed once and
reused for both position cash-flow and previous-row continuity reads.

Added service coverage that would deadlock under sequential execution, proving the support reads
are started concurrently for populated position pages.

## Impact

This reduces `PositionTimeseriesInput:v1` latency for populated analytics pages while preserving
cash-flow inclusion semantics, continuity repair, FX validation, paging, response contracts,
database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused analytics time-series service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
