# CR-573: Market Reference Service Redundant Ranking Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After CR-572 moved current benchmark and composition catalog ranking into the repository SQL layer,
`IntegrationService` still re-applied `latest_effective_records(...)` to already-ranked current
catalog rows when building:

1. `BenchmarkDefinitionResponse`,
2. `BenchmarkCatalogResponse`.

That duplicated source-row selection in the API mapping layer and preserved stale guidance that
current catalog callers should tolerate superseded rows from the repository.

## Change

Removed redundant service-layer latest-effective selection for current benchmark definitions and
current benchmark composition rows. The service now treats the repository as the owner of current
SQL-ranked catalog rows and only keeps `latest_effective_records(...)` for overlapping-window
definition rows, where the service still needs a window-specific resolution step.

## Impact

Benchmark catalog API mapping now avoids unnecessary Python sorting/deduplication after SQL ranking
and keeps current-catalog ownership clear: repository methods return current ranked rows; service
methods map them to API DTOs.

No API route shape, response DTO, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
3. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
