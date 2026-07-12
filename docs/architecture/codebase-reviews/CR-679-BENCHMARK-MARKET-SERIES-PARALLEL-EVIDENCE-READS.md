# CR-679: Benchmark Market Series Parallel Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_benchmark_market_series(...)` already bounded benchmark component work by
reading one page of component `index_id` values first, but then loaded component rows, index price
points, index return points, benchmark return points, and optional benchmark-to-target FX context
sequentially. After the page scope is known, those evidence reads are independent and are only
combined during response assembly.

## Change

The service now builds one post-page market evidence read set and resolves it with
`asyncio.gather(...)`. Requested series fields still control which price, return, benchmark-return,
and FX reads are included. Existing target-currency normalization status behavior is preserved,
including identity, missing-FX, and no-FX-context branches.

Added service coverage that would deadlock under sequential execution, proving the component,
index price, index return, benchmark return, and FX evidence reads are started concurrently.
While touching this service, the page-token helper return contracts were also made explicit for
the repo typechecker.

## Impact

This reduces `MarketDataWindow` latency for benchmark market-series requests that need multiple
evidence classes, while preserving component paging, page-token scope validation, response shape,
data-quality metadata, source lineage, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused integration-service concurrency proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m mypy --config-file mypy.ini`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
