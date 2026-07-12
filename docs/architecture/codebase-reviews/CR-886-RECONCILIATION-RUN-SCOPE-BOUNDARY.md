# CR-886 Reconciliation Run Scope Boundary

Date: 2026-06-04

## Scope

Reduce shared operations repository filtering complexity for financial reconciliation run queries
without changing the operations API response contract or query semantics.

## Finding

`OperationsRepository._apply_reconciliation_run_scope` was a C-ranked method at `C (11)`. It mixed
portfolio scoping, as-of visibility, optional started-at visibility, run identity filters,
request/audit identity filters, reconciliation type, business date, epoch, and status filtering in
one chained helper.

That made the reconciliation support API query path harder to review because time visibility,
identity scoping, and run-attribute scoping were not named as separate policy boundaries.

## Action

Split reconciliation run scope construction into named helpers:

1. `_apply_reconciliation_run_time_scope(...)` for as-of and started-at visibility,
2. `_apply_reconciliation_run_identity_scope(...)` for run id, correlation id, requester, and
   dedupe key filters,
3. `_apply_reconciliation_run_attribute_scope(...)` for reconciliation type, business date, and
   epoch filters.

The public repository query methods still call `_apply_reconciliation_run_scope(...)`, preserving
the existing repository boundary and generated SQL semantics.

## Result

`_apply_reconciliation_run_scope` now reports `A (2)` under Radon cyclomatic complexity instead of
`C (11)`. The extracted time, identity, and attribute helpers all report A-ranked complexity.

This is a real shared-filter boundary improvement, but not final closure:
`operations_repository.py` remains `C (0.00)` under Radon maintainability because the repository
module is still very large, and the current C-ranked maintainability hotspot count remains 8.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m pytest tests\integration\services\query_service\test_int_operations_service.py -q -k "reconciliation_runs"`
  => `1 passed, 17 deselected`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
  => `_apply_reconciliation_run_scope - A (2)` and reconciliation run scope helpers A-ranked
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py -s`
  => `operations_repository.py - C (0.00)`
- `make quality-ruff-gate` => clean
- `make quality-ruff-format-gate` => clean
- `make quality-maintainability-gate` => clean
- `make quality-complexity-gate` => clean
- `make typecheck` => clean
- `make quality-bandit-gate` => clean
- `make quality-vulture-source-gate` => clean
- `make quality-deptry-source-gate` => clean

## Wiki Decision

No wiki source update is required for this slice. The change is an internal query-service
repository scope-helper refactor with repository-local architecture and quality evidence; it does
not change operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned product
truth.
