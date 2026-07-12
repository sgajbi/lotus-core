# CR-906: Core Snapshot Data Quality Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` data-quality classification complexity without changing public service
methods, baseline-count behavior, freshness-status normalization, historical-fallback handling,
current-snapshot completeness requirements, or emitted data-quality status values.

## Finding

`CoreSnapshotService._snapshot_data_quality_status` was the final B-ranked method in
`core_snapshot_service.py`, mixing zero-baseline classification, freshness-status normalization,
historical fallback classification, current-snapshot evidence completeness checks, and default
partial classification.

## Action

Extracted `_is_complete_current_snapshot` so the classifier delegates the current-snapshot evidence
predicate while preserving the same `UNKNOWN`, `PARTIAL`, and `COMPLETE` policy.

## Result

`_snapshot_data_quality_status` now reports `A (4)` instead of `B (6)` under Radon cyclomatic
complexity. `_is_complete_current_snapshot` reports `A (3)`. `core_snapshot_service.py` now has no
B/C/D/E/F-ranked methods under Radon cyclomatic complexity. The file remains `C (0.00)` under
Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s | Select-String " - B| - C| - D| - E| - F"`
  => no B-or-worse methods
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
