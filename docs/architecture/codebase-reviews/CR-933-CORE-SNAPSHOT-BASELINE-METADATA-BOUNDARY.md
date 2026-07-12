# CR-933: Core Snapshot Baseline Metadata Boundary

Date: 2026-06-04

## Scope

Move core snapshot baseline freshness metadata, snapshot timestamp selection, and single-epoch
resolution out of `CoreSnapshotService` without changing repository access, fallback behavior,
data-quality classification, response metadata, API contracts, metrics, or database schema.

## Finding

`CoreSnapshotService` still owned pure baseline metadata helpers inline after earlier baseline
position extraction work. The service only needs to resolve baseline rows and positions; freshness
metadata construction, latest timestamp selection, and single-epoch resolution are reusable
calculation policy.

## Action

Extracted `core_snapshot_baseline_metadata.py` with helpers for:

- current snapshot versus historical fallback freshness metadata,
- latest row/state timestamp selection,
- single resolved snapshot epoch selection,
- empty-baseline epoch suppression.

The service now delegates freshness metadata construction to the helper while preserving baseline
row repository reads, position assembly, and response data-quality classification.

## Result

`core_snapshot_service.py` shrank from 1,067 SLOC to 1,018 SLOC and improved from `C (0.00)` to
`C (2.18)` under Radon maintainability. The new `core_snapshot_baseline_metadata.py` module reports
`A (58.44)` under Radon maintainability, with no B-or-worse complexity findings in the scoped
service/helper check output.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_baseline_metadata.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 48 passed
- `python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_metadata.py tests\unit\services\query_service\services\test_core_snapshot_baseline_metadata.py tests\unit\services\query_service\services\test_core_snapshot_service.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_metadata.py tests\unit\services\query_service\services\test_core_snapshot_baseline_metadata.py tests\unit\services\query_service\services\test_core_snapshot_service.py`
  => 4 files already formatted
- `python -m radon raw src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_metadata.py`
  => `core_snapshot_service.py` 1,018 SLOC; `core_snapshot_baseline_metadata.py` 52 SLOC
- `python -m radon mi src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_metadata.py -s`
  => service `C (2.18)`, helper `A (58.44)`
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_metadata.py -s`
  => no B-or-worse complexity findings in the scoped service/helper check output

## Wiki Decision

No wiki source update is required. This is an internal core snapshot metadata extraction that
preserves API contracts, freshness behavior, data-quality classification, operator workflows, and
public documentation truth.
