# CR-551: Reconciliation Portfolio Day Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository latest reconciliation run lookup for a portfolio day
and epoch.

## Finding

`OperationsRepository.get_latest_reconciliation_run_for_portfolio_day(...)` manually applied
portfolio, business-date, epoch, and as-of reconciliation-run predicates while the reconciliation
run scope helper already centralized the run support predicates used by count, list, and detail
reads. That left the portfolio-day latest-run support lookup exposed to predicate drift from the
governed reconciliation run investigation surface.

The portfolio-day lookup intentionally applies both `updated_at <= as_of` and `started_at <= as_of`
when an observation time is supplied, while count/list/detail reads only require the existing
`updated_at` as-of guard.

## Change

1. Extended `_apply_reconciliation_run_scope(...)` with optional business-date and epoch filters.
2. Added opt-in started-at as-of filtering for portfolio-day latest-run reads.
3. Reused the shared scope helper from the portfolio-day latest-run query.
4. Preserved reconciliation run priority ordering, latest started-at ordering, scalar execution
   shape, and response type.

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
is a maintainability hardening slice that keeps portfolio-day reconciliation support evidence
aligned with the governed reconciliation run scope.
