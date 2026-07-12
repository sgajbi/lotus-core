# CR-576: Client Governance Entry Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still constructed client restriction and sustainability preference entry DTOs
inline after the repository had already been hardened to return SQL-ranked latest client governance
source records.

Those mapping blocks repeated list normalization, decimal conversion, boolean coercion, integer
version conversion, and audit field wiring inside the orchestration service. That kept low-level
source-data DTO assembly mixed with supportability, lineage, and runtime metadata decisions.

## Change

Extended `reference_data_mappers.py` with focused client governance entry mappers:

1. `client_restriction_profile_entry(...)`
2. `sustainability_preference_profile_entry(...)`

`IntegrationService` now delegates restriction and sustainability entry construction to the shared
mapper boundary while retaining binding resolution, supportability state selection, lineage, and
source-data product runtime metadata ownership.

## Impact

This reduces duplication in the DPM client governance service layer and keeps restriction-aware and
sustainability-aware DTO mapping consistent with the rest of the client source-data product mapper
boundary. API route shape, response fields, OpenAPI contracts, repository predicates, database
schema, wiki source, and platform contracts are unchanged.

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
