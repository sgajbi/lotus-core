# CR-526: Operations Status Identity Helper Cleanup

Date: 2026-05-31

## Scope

Query-service operations support repository status handling.

## Finding

After CR-509 through CR-524 normalized stored operational statuses and removed function-wrapped
status predicates, `OperationsRepository` still retained several private status expression helpers
that returned the input column unchanged. Those identity helpers no longer encoded normalization or
query behavior, but they made support query code look as though status columns still required a
repository-local expression layer.

## Change

1. Removed identity-only status expression helpers for support jobs, position-state reprocessing,
   reconciliation runs, portfolio-control stages, analytics exports, and snapshot valuation status.
2. Replaced helper calls with direct governed stored status columns.
3. Preserved request-boundary status filter helpers that normalize caller input before comparing to
   stored values.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
4. `rg "_support_job_status_expr|_reprocessing_status_expr|_reconciliation_status_expr|_portfolio_control_status_expr|_snapshot_valuation_status_expr|_analytics_export_status_expr" src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py -n`
5. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Touched-surface ruff passed.
3. Touched-surface format check passed.
4. Dead-helper search returned no matches.
5. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability cleanup that keeps operations support status handling aligned with the
governed stored-value contract.
