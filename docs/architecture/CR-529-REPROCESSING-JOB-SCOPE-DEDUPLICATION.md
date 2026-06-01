# CR-529: Reprocessing Job Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reprocessing job count and list queries.

## Finding

`OperationsRepository.get_reprocessing_jobs_count(...)` and
`OperationsRepository.get_reprocessing_jobs(...)` both rebuilt the same `RESET_WATERMARKS` support
job scope from JSON payload fields:

1. normalized payload `security_id`,
2. payload `earliest_impacted_date`,
3. date-cast impacted date for portfolio-scope proof,
4. the correlated portfolio-scope existence predicate over position history and position state.

Duplicating that scope in the count and list methods made support pagination easier to drift: a
future fix could update the list query without updating the count query, or the reverse.

## Change

1. Added `ResetWatermarkReprocessingJobScope` to hold the shared SQL expressions and predicate.
2. Added `_reset_watermark_reprocessing_job_scope(...)` to construct the governed support scope
   once.
3. Reused that scope in both reprocessing job count and list queries while preserving the existing
   SQL shape, status filter behavior, ordering, and projected response columns.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
4. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Touched-surface ruff passed.
3. Touched-surface format check passed.
4. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability hardening slice that keeps reprocessing support count and list queries aligned
to one reset-watermark job scope.
