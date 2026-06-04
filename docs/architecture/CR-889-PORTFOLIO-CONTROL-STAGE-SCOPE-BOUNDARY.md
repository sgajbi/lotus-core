# CR-889 Portfolio Control Stage Scope Boundary

Date: 2026-06-04

## Scope

Reduce shared operations repository filtering complexity for portfolio control stage queries
without changing query semantics or operations API response contracts.

## Finding

`OperationsRepository._apply_portfolio_control_stage_scope` was a B-ranked method at `B (6)`. It
mixed portfolio-stage base scoping, as-of visibility, stage id filtering, stage name filtering,
business-date filtering, and status filtering in one helper.

That shape made the portfolio-control operations query path less consistent with the named
valuation, aggregation, and reconciliation scope boundaries.

## Action

Split portfolio-control stage scope construction into named helpers:

1. `_apply_portfolio_control_stage_identity_scope(...)` for stage id and stage name filters,
2. `_apply_portfolio_control_stage_attribute_scope(...)` for business-date filtering.

The public repository query methods still call `_apply_portfolio_control_stage_scope(...)`,
preserving the existing repository boundary and generated SQL semantics.

## Result

`_apply_portfolio_control_stage_scope` now reports `A (3)` under Radon cyclomatic complexity
instead of `B (6)`. The extracted portfolio-control stage scope helpers report A-ranked
complexity.

This is a real shared-filter boundary improvement, but not final closure:
`operations_repository.py` remains `C (0.00)` under Radon maintainability because the repository
module is still very large, and the current C-ranked maintainability hotspot count remains 8.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m pytest tests\integration\services\query_service\test_int_operations_service.py -q -k "portfolio_control_stages"`
  => `1 passed, 17 deselected`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
  => `_apply_portfolio_control_stage_scope - A (3)` and portfolio-control stage scope helpers
  A-ranked
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
