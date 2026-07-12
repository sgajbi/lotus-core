# CR-905: Core Snapshot Delta Section Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` delta-section complexity without changing public service methods,
baseline/projected union semantics, zero-default behavior for missing positions, delta quantity,
delta market value, delta weight, row ordering, or response DTOs.

## Finding

`CoreSnapshotService._build_delta_section` was a B-ranked method mixing baseline/projected security
union construction, missing-position defaults, quantity extraction, market-value extraction,
baseline/projected weight calculation, delta arithmetic, and DTO construction.

## Action

Extracted focused helpers:

- `_DeltaPositionValues`
- `_delta_security_ids`
- `_delta_position_values`
- `_delta_weight`
- `_delta_record`

## Result

`_build_delta_section` now reports `A (2)` instead of `B (10)` under Radon cyclomatic complexity.
The extracted delta-section helpers report A-ranked complexity. `core_snapshot_service.py` remains
`C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s`
  => `_build_delta_section - A (2)`; extracted delta-section helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
