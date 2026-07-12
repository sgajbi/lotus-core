# CR-901: Core Snapshot Projection Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` projected-position complexity without changing public service methods,
simulation change semantics, instrument lookup, market-price and FX lookup behavior, cash/zero
filtering, or response DTOs.

## Finding

`CoreSnapshotService._resolve_projected_positions` was an E-ranked method mixing baseline copy,
simulation change normalization, missing instrument seeding, quantity deltas, baseline proportional
valuation, market-price reads, FX reads, projected value application, and output filtering.

## Action

Extracted focused helpers:

- `_baseline_projected_position`
- `_normalized_simulation_changes` / `_normalized_simulation_change`
- `_seed_missing_projected_instruments` / `_missing_projected_security_ids` /
  `_projected_instrument_map` / `_required_projected_instrument` / `_new_projected_position`
- `_apply_projected_position_changes`
- `_value_projected_positions` / `_apply_baseline_projected_values` /
  `_apply_baseline_projected_value`
- `_apply_priced_projected_values` / `_priced_projected_local_values` /
  `_priced_projected_local_value` / `_market_to_portfolio_fx_rates`
- `_filtered_projected_positions` / `_skip_projected_position`

## Result

`_resolve_projected_positions` now reports `A (2)` instead of `E (34)` under Radon cyclomatic
complexity. The extracted projected-position helpers report A-ranked complexity.
`core_snapshot_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff check src\services\query_service\app\services\core_snapshot_service.py`
  => passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s`
  => `_resolve_projected_positions - A (2)`; extracted projected-position helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
