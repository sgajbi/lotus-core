# CR-523: Reconciliation Status Priority Cleanup

Date: 2026-05-31

## Scope

Query-service operations support reads for financial reconciliation runs and findings.

## Finding

Reconciliation run filters already normalize caller status values once and compare directly against
stored lifecycle status values. The run-list priority helper still wrapped
`financial_reconciliation_runs.status` in `upper(trim(...))`, which preserved mixed predicate
guidance after the reconciliation run support indexes were added. The repository also retained a
dead `_finding_severity_expr(...)` helper even though finding list and summary ordering already use
stored governed severities directly.

The reconciliation run and finding tables have raw status/severity indexes. Historical rows needed a
one-time normalization before the remaining priority helper could use stored values directly.

## Change

1. Added Alembic migration `c0f6a7b8c9d0_perf_normalize_reconciliation_status.py` to normalize
   reconciliation run statuses and finding severities to uppercase trimmed values.
2. Changed `_reconciliation_status_expr(...)` to return the stored status column directly.
3. Removed the unused `_finding_severity_expr(...)` helper.
4. Updated operations repository query-shape proof so reconciliation run priority no longer wraps
   status columns in `upper(trim(...))`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0f6a7b8c9d0_perf_normalize_reconciliation_status.py`
6. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0f6a7b8c9d0_perf_normalize_reconciliation_status.py`
7. `git diff --check`

Results:

1. Operations repository proof passed.
2. Alembic head proof passed.
3. Migration SQL smoke passed.
4. Unit-db migration apply suite passed.
5. Touched-surface ruff passed.
6. Touched-surface format check passed.
7. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is support-query
predicate cleanup for existing reconciliation operations APIs and storage contracts.
