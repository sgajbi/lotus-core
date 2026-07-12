# CR-682: Asset Allocation Parallel Conversion Component Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`ReportingService._resolve_allocation_rows(...)` normalized parent security IDs, converted each
snapshot row into reporting currency sequentially, and only then read look-through component
evidence. Once parent IDs and native row values are collected, the row-level FX conversions and the
component evidence lookup are independent.

## Change

The service now collects row inputs first, starts all reporting-currency conversions, and reads
look-through components in the same `asyncio.gather(...)` fan-out. Converted values are then
rejoined to rows in deterministic order before the existing direct and look-through allocation
logic runs.

Added service coverage that would deadlock under sequential execution, proving row conversions and
component evidence reads are started concurrently.

## Impact

This reduces `AssetAllocation` latency for populated reporting scopes, especially when
look-through support is requested, while preserving parent-security normalization, direct-only and
prefer-look-through behavior, component weighting rules, response shape, database schema, wiki
source, and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service allocation proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
