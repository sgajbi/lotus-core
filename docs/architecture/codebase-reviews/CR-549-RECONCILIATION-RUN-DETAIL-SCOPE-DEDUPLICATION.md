# CR-549: Reconciliation Run Detail Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reconciliation run detail read.

## Finding

`OperationsRepository.get_reconciliation_run(...)` manually applied the same portfolio, run-id, and
as-of scope already centralized for reconciliation run count/list reads. That left the direct
reconciliation run detail path exposed to predicate drift from the paged reconciliation support
surface.

The detail read intentionally needs only portfolio, run id, and as-of filtering. It must not inherit
status, correlation id, requested-by, dedupe-key, or reconciliation-type filters.

## Change

1. Reused `_apply_reconciliation_run_scope(...)` for the reconciliation run detail query.
2. Passed only `portfolio_id`, `run_id`, and `as_of`.
3. Preserved scalar execution shape, as-of `updated_at` guard, and response type.

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
is a maintainability hardening slice that keeps direct reconciliation run detail evidence aligned
with the governed reconciliation support run scope.
