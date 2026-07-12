# CR-581: Market Reference Series Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still assembled several market/reference DTO records inline after the
repository layer had been hardened to SQL-rank canonical provider rows:

1. index price series points,
2. index return series points,
3. benchmark return series points,
4. risk-free series points,
5. classification taxonomy entries.

Those blocks repeated decimal conversion and field wiring inside response orchestration methods that
also own fingerprints, lineage, supportability, and runtime metadata.

## Change

Extended `reference_data_mappers.py` with market/reference series mappers:

1. `index_price_series_point(...)`
2. `index_return_series_point(...)`
3. `benchmark_return_series_point(...)`
4. `risk_free_series_point(...)`
5. `classification_taxonomy_entry(...)`

The integration service now delegates those row-to-DTO conversions to the shared mapper boundary
while retaining request fingerprints, resolved windows, lineage envelopes, data-quality status, and
runtime metadata ownership.

## Impact

This keeps market/reference series and taxonomy DTO semantics in one tested mapper layer and
continues the service modularization after the SQL-ranking performance work. API route shape,
response fields, OpenAPI contracts, repository predicates, database schema, wiki source, and
platform contracts are unchanged.

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
