# CR-509: Analytics Export Status Predicate Hardening

Date: 2026-05-29

## Scope

Query-service operations support reads for analytics export job health and job listings.

## Finding

Analytics export writers persist governed lowercase statuses such as `accepted`, `running`,
`completed`, and `failed`, and the table already carries status-oriented indexes. Operations
support queries still wrapped stored status values in `lower(trim(...))` for filters and priority
classification. That made filtered support queries less able to use the existing status indexes and
kept the persisted data contract implicit.

## Change

1. Added Alembic migration `c0e4f5a6b7c8_perf_normalize_analytics_export_status.py` to normalize
   existing analytics export status values to lowercase trimmed governed values.
2. Changed analytics export status predicates and priority classification in
   `OperationsRepository` to use stored governed status values directly.
3. Updated repository query-shape tests to prove status filters no longer wrap indexed status
   columns in SQL functions.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories tests/unit/services/financial_reconciliation_service -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e4f5a6b7c8_perf_normalize_analytics_export_status.py`
6. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e4f5a6b7c8_perf_normalize_analytics_export_status.py`
7. `git diff --check`

Results:

1. Focused operations repository proof: `67 passed`
2. Affected model/query-service repository/financial reconciliation proof: `242 passed`
3. Alembic head proof: `c0e4f5a6b7c8 (head)`
4. Migration contract smoke: passed
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is a storage-contract
and query-predicate hardening change for existing operations support endpoints.
