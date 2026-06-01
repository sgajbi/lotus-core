# CR-668: Cashflow Projection Parallel Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashflowProjectionService.get_cashflow_projection(...)` resolved the portfolio and date window,
then read booked cashflow evidence and projected settlement cashflow evidence sequentially. For
projected windows these reads are independent and use separate repository queries over booked
cashflows and settlement-dated external cash movements.

## Change

For `include_projected=True`, the service now reads booked cashflow evidence and projected
settlement evidence with `asyncio.gather(...)`. The booked-only path remains a single booked
cashflow read and still skips the projected settlement query.

Added service coverage that would deadlock under sequential execution, proving the two evidence
reads are started concurrently for projected windows.

## Impact

This reduces cashflow projection latency for projected windows without changing route shape,
response contracts, database schema, data-quality metadata, source-batch fingerprints, wiki source,
or platform contracts.

## Validation

Local validation passed:

1. focused cashflow projection service proof
2. focused cashflow repository query-shape proof
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
