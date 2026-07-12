# CR-904: Core Snapshot Simulation Validation Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` simulation validation complexity without changing public service
methods, required simulation-option behavior, session lookup behavior, portfolio ownership checks,
expected-version checks, error types, or error messages.

## Finding

`CoreSnapshotService._validated_simulation_session` was a B-ranked method mixing simulation-option
presence validation, repository lookup, missing-session handling, portfolio ownership validation,
expected-version validation, and session return.

## Action

Extracted focused helpers:

- `_required_simulation_options`
- `_required_simulation_session`
- `_validate_simulation_portfolio`
- `_validate_simulation_version`

## Result

`_validated_simulation_session` now reports `A (1)` instead of `B (6)` under Radon cyclomatic
complexity. The extracted simulation-validation helpers report A-ranked complexity.
`core_snapshot_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s`
  => `_validated_simulation_session - A (1)`; extracted simulation-validation helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
