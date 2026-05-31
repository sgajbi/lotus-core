# CR-574: Market Reference DTO Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still owned repetitive market/reference DTO construction for benchmark
definition, benchmark catalog, benchmark component, and index catalog responses. That kept mapping
logic inside an already large orchestration service and duplicated the same benchmark component
payload shape in multiple methods.

The duplication was not a contract bug, but it made the service harder to maintain and increased
the chance that benchmark definition and benchmark catalog responses would drift.

## Change

Added `reference_data_mappers.py` for market/reference DTO mapping:

1. `benchmark_component_response(...)`
2. `benchmark_definition_response(...)`
3. `index_definition_response(...)`

`IntegrationService` now delegates benchmark and index catalog DTO construction to the mapper
module and keeps the service focused on orchestration, repository calls, pagination, and
supportability logic.

## Impact

This reduces duplication in the query-service integration layer and creates a reusable mapper
boundary for future market/reference DTO hardening. API route shape, response fields, OpenAPI
contracts, repository predicates, database schema, wiki source, and platform contracts are
unchanged.

No wiki update was needed because this is an internal service-boundary cleanup with no user-facing
feature, operating model, or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_reference_data_mappers.py tests/unit/services/query_service/services/test_integration_service.py -q` - 101 passed
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
3. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
