# CR-582: Benchmark Market Series Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_benchmark_market_series(...)` still assembled benchmark component market
series DTOs inline. The loop mixed selected-field projection, decimal conversion for index price,
index return, benchmark return, component weight, FX context, series-currency selection, and quality
status propagation with paging, evidence row selection, supportability, lineage, and runtime
metadata.

That kept a complex market/reference response mapping block inside the large orchestration service
after the repository layer had already been hardened for canonical SQL-ranked market series reads.

## Change

Extended `reference_data_mappers.py` with benchmark market-series mappers:

1. `benchmark_market_series_point(...)`
2. `benchmark_component_series_response(...)`

The integration service now delegates component point and component-series DTO construction to the
shared mapper boundary while retaining FX lookup decisions, pagination, evidence-row aggregation,
quality-summary aggregation, lineage, and runtime metadata ownership.

## Impact

This keeps benchmark component market-series DTO semantics in one tested mapper layer and further
narrows the integration service toward orchestration. API route shape, response fields, OpenAPI
contracts, repository predicates, database schema, wiki source, and platform contracts are
unchanged.

No wiki update was needed because this is an internal mapper extraction with no user-facing feature,
operating model, or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_reference_data_mappers.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
