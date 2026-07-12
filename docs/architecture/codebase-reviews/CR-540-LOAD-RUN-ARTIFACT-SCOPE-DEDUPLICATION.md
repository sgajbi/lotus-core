# CR-540: Load Run Artifact Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository load-run progress reads.

## Finding

`OperationsRepository.get_load_run_progress(...)` maintained the same artifact-read scope across
daily position snapshots, position timeseries, and portfolio timeseries:

1. load-run portfolio id prefix,
2. optional business-date evidence slice,
3. optional as-of materialization guard.

The repeated predicates appeared in both count queries and latest-materialization queries. This
preserved correct behavior, but it made a high-volume support progress endpoint vulnerable to
future drift between artifact families or between count and latest-read statements.

## Change

1. Added `_apply_load_run_artifact_scope(...)` for shared load-run artifact predicates.
2. Reused it for snapshot, position-timeseries, and portfolio-timeseries counts and latest
   materialization reads.
3. Preserved existing `LIKE` load-run portfolio matching, business-date predicates, as-of
   `created_at` guards, scalar execution order, and response shape.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
6. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Alembic reported a single current head.
3. Migration SQL contract smoke passed.
4. Touched-surface ruff passed.
5. Touched-surface format check passed.
6. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability hardening slice that keeps load-run artifact support reads aligned to one
governed materialization scope.
