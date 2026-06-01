# CR-681: AUM Snapshot Row Parallel Conversions

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`ReportingService.get_assets_under_management(...)` loaded the latest snapshot rows for the
resolved portfolio scope, then converted each row's market value into the reporting currency
sequentially before aggregating portfolio and total AUM. Once the snapshot rows and reporting
currency are known, those row-level conversions are independent.

## Change

The service now builds the native market-value row set first, resolves all row-level reporting
currency conversions with `asyncio.gather(...)`, and then applies the converted values to the
existing per-portfolio aggregation loop in deterministic row order.

Added service coverage that would deadlock under sequential execution, proving snapshot-row
conversions are started concurrently for AUM reporting.

## Impact

This reduces `AssetsUnderManagement` latency for multi-position and multi-portfolio reporting
scopes while preserving portfolio aggregation, native portfolio totals, reporting totals,
same-currency conversion behavior, missing-rate failure behavior, response shape, database schema,
wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service AUM proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
