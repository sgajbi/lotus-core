# CR-535: Reprocessing Job Filter Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reset-watermarks reprocessing-job count and list
queries.

## Finding

`OperationsRepository.get_reprocessing_jobs_count(...)` and
`OperationsRepository.get_reprocessing_jobs(...)` both maintained the same support filter scope:

1. `RESET_WATERMARKS` job type,
2. correlated portfolio ownership through impacted position history,
3. as-of support evidence guard,
4. governed stored job status predicate,
5. normalized payload security identifier predicate,
6. job id,
7. correlation id.

CR-529 centralized the reset-watermark payload expressions and correlated portfolio-scope
predicate, but the count and list queries still duplicated the application of those filters. That
left valuation reprocessing support pagination exposed to future count/list drift.

## Change

1. Added `_apply_reprocessing_job_scope(...)` as the shared reset-watermarks reprocessing-job
   filter helper.
2. Reused that helper from both reprocessing-job count and list queries.
3. Preserved existing invalid-security short-circuit behavior, direct stored-status comparisons,
   normalized payload-security predicate, correlated active-position scope, stale-priority
   ordering, projection labels, offset/limit semantics, and response shape.

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
is a maintainability hardening slice that keeps valuation reprocessing job support pagination
aligned to one governed filter scope.
