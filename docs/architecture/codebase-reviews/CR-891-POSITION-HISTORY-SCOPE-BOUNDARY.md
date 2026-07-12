# CR-891: Position History Scope Boundary

Date: 2026-06-04

## Scope

Reduce `OperationsRepository` filtering complexity for current position history queries without
changing query semantics, public repository methods, or API response contracts.

## Finding

`OperationsRepository._apply_current_position_history_scope` was a B-ranked helper that mixed
security expression resolution, `PositionHistory` / `PositionState` join construction, normalized
security filtering, history-date cutoff handling, and `history_as_of` visibility rules in one
method.

That made a shared position history query boundary harder to review and harder to safely extend.

## Action

Split the current position history scope into named helper boundaries:

- `_position_history_security_expressions(...)` resolves the security-id expression pair used by
  `PositionHistory` and `PositionState`.
- `_apply_position_history_security_scope(...)` applies normalized security filtering while
  preserving existing null and empty-string behavior.
- `_apply_position_history_time_scope(...)` applies history-date cutoff and `history_as_of`
  visibility filtering.

The public repository methods and SQL semantics remain unchanged.

## Result

`_apply_current_position_history_scope` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity. The extracted helper methods also report A-ranked complexity:

- `_position_history_security_expressions` => `A (3)`
- `_apply_position_history_security_scope` => `A (2)`
- `_apply_position_history_time_scope` => `A (3)`

`operations_repository.py` remains `C (0.00)` under Radon maintainability, so the source
C-hotspot count remains 8.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py`
- `make quality-ruff-gate`
- `make quality-ruff-format-gate`
- `make quality-complexity-gate`
- `make quality-maintainability-gate`
- `make typecheck`
- `make quality-bandit-gate`
- `make quality-vulture-source-gate`
- `make quality-deptry-source-gate`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py -s`
- `python -m radon mi src -s`

No integration selection was run for this slice. The change is an internal SQL-scope helper
refactor backed by the operations repository unit suite and enforced source quality gates.

## Wiki Decision

No wiki source update is required. This is an internal repository scope-helper refactor and does
not change an operator-facing contract, API contract, or runbook.
