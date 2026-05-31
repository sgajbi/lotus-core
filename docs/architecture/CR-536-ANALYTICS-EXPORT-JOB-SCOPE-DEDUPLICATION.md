# CR-536: Analytics Export Job Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository analytics-export job count and list queries.

## Finding

`OperationsRepository.get_analytics_export_jobs_count(...)` and
`OperationsRepository.get_analytics_export_jobs(...)` both maintained the same support scope:

1. portfolio ownership,
2. as-of support evidence guard,
3. governed stored export status predicate,
4. export job id,
5. request fingerprint.

Duplicating that scope made analytics export support pagination vulnerable to future count/list
drift when adding or correcting operational filters.

## Change

1. Added `_apply_analytics_export_job_scope(...)` as the shared analytics-export job filter helper.
2. Reused that helper from both analytics-export job count and list queries.
3. Preserved existing direct stored-status comparisons, stale-priority ordering, offset/limit
   semantics, and response shape.

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
is a maintainability hardening slice that keeps analytics-export support pagination aligned to one
governed filter scope.
