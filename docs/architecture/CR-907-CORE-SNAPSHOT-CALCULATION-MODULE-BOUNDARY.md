# CR-907: Core Snapshot Calculation Module Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` module size and calculation responsibility without changing public
service methods, baseline/projected total semantics, position weight assignment, delta-section
ordering, missing-position zero defaults, delta arithmetic, or response DTOs.

## Finding

`core_snapshot_service.py` had no B-or-worse methods after CR-906, but it remained a C-ranked
maintainability hotspot because it still carried calculation helpers for market-value totals,
position-record weight assignment, and delta-section construction in the service module.

## Action

Extracted calculation helpers into `core_snapshot_calculations.py`:

- `total_market_value_baseline`
- `total_market_value_projected`
- `assign_baseline_weights`
- `assign_projected_weights`
- `build_delta_section`
- `DeltaPositionValues` and private delta helper functions

Updated service callers and focused unit tests to target the extracted calculation module.

## Result

`core_snapshot_calculations.py` reports `A (43.88)` under Radon maintainability and has no
B-or-worse methods under Radon cyclomatic complexity. `core_snapshot_service.py` remains
`C (0.00)` under Radon maintainability, but its raw source size decreased from 1,208 SLOC / 518
LLOC to 1,093 SLOC / 464 LLOC. The C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_calculations.py tests\unit\services\query_service\services\test_core_snapshot_service.py`
  => formatted
- `python -m radon mi src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_calculations.py -s`
  => `core_snapshot_service.py - C (0.00)`, `core_snapshot_calculations.py - A (43.88)`
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_calculations.py -s | Select-String " - B| - C| - D| - E| - F"`
  => no B-or-worse methods
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper module extraction that
preserves API contracts, supported features, operator workflows, and public documentation truth.
