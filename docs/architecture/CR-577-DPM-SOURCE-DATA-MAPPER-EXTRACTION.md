# CR-577: DPM Source-Data Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still assembled several DPM source-data DTOs inline:

1. model portfolio target rows,
2. portfolio-manager book members,
3. CIO model-change affected mandates,
4. DPM portfolio-universe candidates.

Those blocks repeated decimal conversion, binding-version coercion, and source-lineage field wiring
inside the orchestration service. The result was a larger service surface where mapping drift could
appear independently from repository query hardening and source-data product supportability logic.

## Change

Extended `reference_data_mappers.py` with focused DPM source-data mappers:

1. `model_portfolio_target_row(...)`
2. `portfolio_manager_book_member(...)`
3. `cio_model_change_affected_mandate(...)`
4. `dpm_portfolio_universe_candidate(...)`

The integration service now delegates those row-to-DTO conversions to the shared mapper boundary
while retaining pagination, supportability state selection, lineage envelopes, runtime metadata,
and deterministic snapshot identity ownership.

## Impact

This narrows the large DPM integration service toward orchestration and keeps DPM model, book,
cohort, and universe DTO construction in one tested mapper layer. API route shape, response fields,
OpenAPI contracts, repository predicates, database schema, wiki source, and platform contracts are
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
