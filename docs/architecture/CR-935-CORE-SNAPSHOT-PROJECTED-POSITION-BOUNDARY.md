# CR-935: Core Snapshot Projected Position Boundary

Date: 2026-06-04

## Scope

Move deterministic projected-position mapping out of `CoreSnapshotService` without changing
simulation change reads, instrument reads, market-price reads, FX reads, projected valuation
semantics, cash/zero filtering, API contracts, metrics, or database schema.

## Finding

`CoreSnapshotService` still owned pure projected-position mutation and filtering logic inline after
the async simulation, instrument, price, and FX orchestration had already been separated into
smaller service methods. The service only needs to coordinate repository reads, missing-instrument
resolution, priced valuation reads, and error mapping; deterministic position copying, transaction
quantity application, baseline valuation reuse, and cash/zero filtering are reusable projection
policy.

## Action

Extracted `core_snapshot_projected_positions.py` with helpers for:

- baseline-to-projected position copying,
- missing projected security-id discovery,
- new projected instrument payload construction,
- projected quantity mutation from transaction effects,
- baseline unit-value reuse and positive new-position pricing requirements,
- cash and zero-position filtering.

The service now delegates deterministic projected-position policy to the helper while preserving
repository orchestration, unavailable-section errors, priced valuation reads, FX conversion, and
deterministic output sorting.

## Result

`core_snapshot_service.py` shrank from 896 SLOC to 789 SLOC and improved from `C (6.12)` to
`B (12.41)` under Radon maintainability. The new `core_snapshot_projected_positions.py` module
reports `A (42.61)` under Radon maintainability, with no B-or-worse complexity findings in the
scoped service/helper check output. This removes `core_snapshot_service.py` from the active
C-ranked maintainability hotspot list; the generated `query_service/build` copy remains separate
generated-surface debt.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_projected_positions.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 51 passed
- `python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_projected_positions.py tests\unit\services\query_service\services\test_core_snapshot_projected_positions.py tests\unit\services\query_service\services\test_core_snapshot_service.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_projected_positions.py tests\unit\services\query_service\services\test_core_snapshot_projected_positions.py tests\unit\services\query_service\services\test_core_snapshot_service.py`
  => 4 files already formatted
- `python -m radon raw src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_projected_positions.py`
  => `core_snapshot_service.py` 789 SLOC; `core_snapshot_projected_positions.py` 104 SLOC
- `python -m radon mi src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_projected_positions.py -s`
  => service `B (12.41)`, helper `A (42.61)`
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_projected_positions.py -s`
  => no B-or-worse complexity findings in the scoped service/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal core snapshot projection-policy extraction
that preserves API contracts, simulation projection behavior, valuation behavior, operator
workflows, and public documentation truth.
