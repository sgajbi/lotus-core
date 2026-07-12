# CR-519: Client Source Index Hardening

Date: 2026-05-31

## Scope

Query-service source-data reads for client restriction, sustainability, tax, income, liquidity
reserve, and planned withdrawal evidence:

1. `ClientRestrictionProfile:v1`
2. `SustainabilityPreferenceProfile:v1`
3. `ClientTaxProfile:v1`
4. `ClientTaxRuleSet:v1`
5. `ClientIncomeNeedsSchedule:v1`
6. `LiquidityReserveRequirement:v1`
7. `PlannedWithdrawalSchedule:v1`

## Finding

These reads filter by portfolio, client, optional mandate, active lifecycle status, and effective
or scheduled-date windows before ordering by source-specific identity and latest evidence metadata.
The tables only declared generic portfolio/client effective-window indexes, while repository
predicates wrapped lifecycle status columns in `lower(trim(...))`.

The ingestion DTOs constrain these lifecycle fields to governed lowercase values, so the read path
can compare directly against stored status values after migration-time canonicalization.

## Change

1. Added partial active-source indexes for each client source-data evidence table.
2. Added Alembic migration `c0f3a4b5c6d7_perf_add_client_source_indexes.py` to normalize existing
   lifecycle statuses and create the partial indexes.
3. Changed the client source-data repository predicates to compare directly against governed stored
   lifecycle values.
4. Added model metadata proof and query-shape proof that these source-data reads no longer wrap
   lifecycle status columns.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f3a4b5c6d7_perf_add_client_source_indexes.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f3a4b5c6d7_perf_add_client_source_indexes.py`
7. `git diff --check`

Results:

1. Focused model and reference-data repository proof: `42 passed`
2. Alembic head proof: `c0f3a4b5c6d7 (head)`
3. Migration SQL smoke: passed
4. Unit-db migration apply suite: `9 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape or platform contract change was required. This is a storage-contract hardening
change for existing DPM client source-data evidence queries.
