# CR-452: Model Portfolio Write-Boundary Base-Currency Canonicalization

Date: 2026-05-28

## Scope

Model portfolio reference-data ingestion DTOs, reference-data upsert preparation, and route-level
persistence behavior.

## Finding

Model portfolio definitions drive target model construction, mandate alignment, rebalancing, and
benchmark policy workflows. `base_currency` was accepted as raw caller text in the reference-data
write path, so padded or lower-case values could become authoritative model master data and create
avoidable downstream normalization work in advisory and rebalancing calculations.

## Change

Reused the shared portfolio-common currency-code normalizer at the model-portfolio definition
write boundaries:

1. `ModelPortfolioDefinitionRecord` validates and canonicalizes `base_currency` before route
   handling,
2. `ReferenceDataIngestionService.upsert_model_portfolio_definitions(...)` canonicalizes direct
   service input before constructing the database upsert,
3. route-level integration proof now persists padded lower-case model base currency as canonical
   `SGD`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py -q -k model_portfolio_definition_normalizes_base_currency`
2. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q -k "model_portfolio_definitions_normalizes_base_currency or upsert_model_portfolio_definitions"`
3. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k ingest_model_portfolios_normalizes_base_currency`
4. `python -m ruff check src/services/ingestion_service/app/DTOs/reference_data_dto.py src/services/ingestion_service/app/services/reference_data_ingestion_service.py tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
5. `python -m pytest tests/unit/services/ingestion_service -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `git diff --check`

Results:

1. Focused DTO pytest: `1 passed, 23 deselected`
2. Focused reference-data service pytest: `2 passed, 18 deselected`
3. Focused ingestion router pytest: `1 passed, 207 deselected`
4. Touched-surface ruff: passed
5. Ingestion-service unit pack: `100 passed`
6. Ingestion router integration pack: `208 passed`
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: valid model portfolio base currency values are
canonicalized and invalid non-three-letter values are rejected before persistence.
