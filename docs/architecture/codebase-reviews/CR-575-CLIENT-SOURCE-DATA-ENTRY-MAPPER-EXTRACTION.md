# CR-575: Client Source-Data Entry Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still constructed client source-data entry DTOs inline for tax, tax-rule,
income-needs, liquidity-reserve, and planned-withdrawal products. The mapping blocks repeated
decimal conversion, list normalization, integer conversion, and source-record field wiring inside
the orchestration service.

This kept low-level DTO mapping mixed into business orchestration and made future DPM client
source-data contract hardening more likely to drift across product families.

## Change

Extended `reference_data_mappers.py` with focused client source-data entry mappers:

1. `client_tax_profile_entry(...)`
2. `client_tax_rule_set_entry(...)`
3. `client_income_needs_schedule_entry(...)`
4. `liquidity_reserve_requirement_entry(...)`
5. `planned_withdrawal_schedule_entry(...)`

`IntegrationService` now delegates those entry mappings to the shared mapper boundary while
retaining orchestration, supportability state selection, lineage, and runtime metadata ownership.

## Impact

This reduces duplication in the DPM client source-data service layer and keeps DTO construction
consistent across tax, income, liquidity, and withdrawal evidence products. API route shape,
response fields, OpenAPI contracts, repository predicates, database schema, wiki source, and
platform contracts are unchanged.

No wiki update was needed because this is an internal mapper extraction with no user-facing feature,
operating model, or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_reference_data_mappers.py tests/unit/services/query_service/services/test_integration_service.py -q` - 103 passed
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
3. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
