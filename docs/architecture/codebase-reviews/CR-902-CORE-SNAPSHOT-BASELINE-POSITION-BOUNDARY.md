# CR-902: Core Snapshot Baseline Position Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` baseline-position complexity without changing public service methods,
current-position versus history fallback behavior, quantity/cash/zero filtering, market-value
selection, weight assignment, freshness metadata, or response DTOs.

## Finding

`CoreSnapshotService._resolve_baseline_positions` was a D-ranked method mixing current snapshot
lookup, historical fallback lookup, row filtering, security-id normalization, market-value source
selection, instrument enrichment payload construction, baseline weight assignment, sorting, and
freshness metadata construction.

## Action

Extracted focused helpers:

- `_BaselinePositionRows`
- `_baseline_position_rows`
- `_baseline_position_entry`
- `_skip_baseline_position`
- `_baseline_market_values`
- `_baseline_position_payload`
- `_missing_instrument_payload`
- `_baseline_instrument_payload`
- `_baseline_freshness`
- `_baseline_snapshot_epoch`

## Result

`_resolve_baseline_positions` now reports `A (3)` instead of `D (28)` under Radon cyclomatic
complexity. The extracted baseline-position helpers report A-ranked complexity.
`core_snapshot_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s`
  => `_resolve_baseline_positions - A (3)`; extracted baseline-position helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
