# CR-550: Reconciliation Finding Summary Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reconciliation finding summary aggregate.

## Finding

`OperationsRepository.get_reconciliation_finding_summary(...)` manually applied the same run-id and
as-of finding scope already centralized for reconciliation finding list/count reads. That left the
summary aggregate exposed to predicate drift from paged reconciliation finding investigation reads.

The summary intentionally needs all findings for a run at the requested observation time, so only
run-id and as-of filtering should be applied.

## Change

1. Reused `_apply_reconciliation_finding_scope(...)` for the finding-summary base query.
2. Passed only `run_id` and `as_of` so finding-id, security, and transaction filters remain absent.
3. Preserved aggregate definitions, top-blocking ordering, normalized security output, and response
   type.

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
is a maintainability hardening slice that keeps reconciliation finding summary evidence aligned
with the governed reconciliation finding support scope.
