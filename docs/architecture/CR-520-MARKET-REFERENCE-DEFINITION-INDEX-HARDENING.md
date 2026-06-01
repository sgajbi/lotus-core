# CR-520: Market Reference Definition Index Hardening

Date: 2026-05-31

## Scope

Query-service source-data reads for market/reference definition evidence:

1. benchmark definitions
2. index definitions

## Finding

Benchmark and index definition reads filter by effective-date window, optional type/currency/id
criteria, and governed lifecycle status before ordering by identifier and latest effective date.
The status predicates used `lower(trim(...))`, which prevented direct use of status-aware indexes
even though ingestion canonicalizes source statuses to lowercase values. The tables also lacked a
partial active/effective ordering index for these source-data reads.

## Change

1. Added partial active definition indexes for benchmark and index definitions on identifier,
   latest effective date, and effective end date.
2. Added Alembic migration `c0f4a5b6c7d8_perf_add_market_reference_definition_indexes.py` to
   normalize existing lifecycle statuses and create the partial indexes.
3. Changed benchmark/index definition predicates to compare directly against normalized stored
   lifecycle values.
4. Added model metadata proof and query-shape proof that the reads no longer wrap lifecycle status
   columns.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f4a5b6c7d8_perf_add_market_reference_definition_indexes.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f4a5b6c7d8_perf_add_market_reference_definition_indexes.py`
7. `git diff --check`

Results:

1. Focused model and reference-data repository proof: `43 passed`
2. Alembic head proof: `c0f4a5b6c7d8 (head)`
3. Migration SQL smoke: passed
4. Unit-db migration apply suite: `9 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape or platform contract change was required. This is a storage-contract hardening
change for existing market/reference definition evidence queries.
