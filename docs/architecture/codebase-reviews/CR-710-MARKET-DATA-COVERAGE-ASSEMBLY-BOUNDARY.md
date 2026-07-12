# CR-710: Market Data Coverage Assembly Boundary

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_market_data_coverage(...)` mixed repository orchestration with source-data
product response assembly: request-scope normalization, repository lookup de-duplication,
per-instrument/per-FX coverage mapping, supportability classification, lineage, and runtime
metadata. This kept DPM market-data readiness policy embedded in the large integration service and
made future source-data product changes harder to test independently.

## Change

Added `market_data_coverage.py` as the focused market-data coverage assembly boundary. The
integration service now resolves the read scope, performs the two repository reads, and delegates
response assembly to the helper. Focused tests cover read-scope normalization/de-duplication,
ready runtime lineage, stale classification, and missing evidence classification.

## Impact

This reduces `IntegrationService` policy density while preserving market-price and FX predicates,
response shape, supportability reason codes, lineage, source-data product metadata, and DPM
readiness behavior. No API route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. focused market-data coverage helper and integration-service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
