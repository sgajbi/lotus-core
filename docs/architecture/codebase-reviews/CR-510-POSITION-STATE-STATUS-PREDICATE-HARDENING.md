# CR-510: Position State Status Predicate Hardening

Date: 2026-05-29

## Scope

Query-service operations support reads for reprocessing lineage keys and position-state
reprocessing keys.

## Finding

`position_state.status` is a governed uppercase operational status with model defaults and
integration fixtures using values such as `CURRENT` and `REPROCESSING`. The table has status-led
indexes for scheduler and support scans, but operations support filters and priority classification
still wrapped the stored value in `upper(trim(...))`.

That function-wrapped predicate can prevent direct use of existing `position_state.status` indexes
for lineage and reprocessing-key drilldowns, which are operator-facing hot paths during replay,
backfill, and valuation recovery.

## Change

1. Added Alembic migration `c0e5f6a7b8c9_perf_normalize_position_state_status.py` to normalize
   existing `position_state.status` values to uppercase trimmed governed values.
2. Changed operations repository reprocessing status predicates and priority classification to use
   stored governed status values directly.
3. Updated repository query-shape tests to prove status filters no longer wrap indexed
   `position_state.status` columns in SQL functions.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories tests/unit/services/financial_reconciliation_service -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e5f6a7b8c9_perf_normalize_position_state_status.py`
6. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e5f6a7b8c9_perf_normalize_position_state_status.py`
7. `git diff --check`

Results:

1. Focused operations repository proof: `67 passed`
2. Affected model/query-service repository/financial reconciliation proof: `242 passed`
3. Alembic head proof: `c0e5f6a7b8c9 (head)`
4. Migration contract smoke: passed
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is a storage-contract
and query-predicate hardening change for existing operations support endpoints.
