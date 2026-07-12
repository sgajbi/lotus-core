# CR-701: Operations Count/Page Read Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`OperationsService` repeated the same `asyncio.gather(...)` count/page orchestration across
operator drilldown endpoints for lineage keys, valuation jobs, aggregation jobs, analytics exports,
reconciliation runs/findings, control stages, reprocessing keys, and reprocessing jobs. The repeated
pattern made support-list concurrency easy to drift endpoint by endpoint as the operations surface
continues to grow.

## Change

Added `_read_count_and_page(...)` as the shared operations-service helper for independent count and
page reads, and routed the existing operations support list endpoints through it. The helper keeps
the existing count/page concurrency explicit while leaving each endpoint's filters, normalization,
response DTO assembly, generated-at snapshot, and evidence metadata unchanged.

Added focused coverage proving the helper starts count and page reads concurrently.

## Impact

This reduces duplicated operations support orchestration while preserving support-list latency,
pagination behavior, status/security/correlation filters, response shape, database schema, wiki
source, and platform contracts.

## Validation

Local validation passed:

1. focused operations-service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
