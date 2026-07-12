# CR-537: Valuation Job Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository valuation-job count and list queries.

## Finding

`OperationsRepository.get_valuation_jobs_count(...)` and
`OperationsRepository.get_valuation_jobs(...)` both maintained the same support scope:

1. portfolio ownership,
2. actionable valuation-job filtering that hides superseded pending rows unless a direct job or
   correlation lookup is requested,
3. as-of support evidence guard,
4. governed stored job status predicate,
5. valuation business date,
6. normalized security identifier predicate,
7. job id,
8. correlation id.

Duplicating that scope made valuation operations pagination vulnerable to future count/list drift,
especially around the actionable-job guard that protects support views from stale superseded
pending work while preserving direct lookup semantics.

## Change

1. Added `_apply_valuation_job_scope(...)` as the shared valuation-job filter helper.
2. Reused that helper from both valuation-job count and list queries.
3. Preserved existing invalid-security short-circuit behavior, actionable-job bypass semantics,
   direct stored-status comparisons, normalized security predicate, stale-priority ordering,
   offset/limit semantics, and response shape.

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
is a maintainability hardening slice that keeps valuation operations pagination aligned to one
governed filter scope.
