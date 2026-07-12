# CR-934: Core Snapshot Baseline Position Boundary

Date: 2026-06-04

## Scope

Move core snapshot baseline row-to-position mapping out of `CoreSnapshotService` without changing
repository access, current-versus-history source selection, cash/zero filtering, security-id
normalization, market-value handling, instrument enrichment payloads, API contracts, metrics, or
database schema.

## Finding

`CoreSnapshotService` still owned pure baseline position mapping helpers inline after baseline row
selection and freshness metadata had been isolated. The service only needs to read baseline rows,
assemble the resulting map, apply weights, and return freshness metadata; row filtering, value
selection, and instrument payload construction are reusable mapping policy.

## Action

Extracted `core_snapshot_baseline_positions.py` with helpers for:

- baseline row iteration and deterministic sorting,
- quantity and security-id normalization,
- cash and zero-position filtering,
- snapshot market-value versus historical cost-basis selection,
- missing-instrument fallback payloads,
- instrument-enrichment payload construction.

The service now delegates row mapping to the helper while preserving repository reads, baseline
weight assignment, and freshness metadata construction.

## Result

`core_snapshot_service.py` shrank from 1,018 SLOC to 896 SLOC and improved from `C (2.18)` to
`C (6.12)` under Radon maintainability. The new `core_snapshot_baseline_positions.py` module
reports `A (45.13)` under Radon maintainability, with no B-or-worse complexity findings in the
scoped service/helper check output.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_baseline_positions.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 48 passed
- `python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_positions.py tests\unit\services\query_service\services\test_core_snapshot_baseline_positions.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_positions.py tests\unit\services\query_service\services\test_core_snapshot_baseline_positions.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_positions.py`
  => `core_snapshot_service.py` 896 SLOC; `core_snapshot_baseline_positions.py` 137 SLOC
- `python -m radon mi src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_positions.py -s`
  => service `C (6.12)`, helper `A (45.13)`
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_baseline_positions.py -s`
  => no B-or-worse complexity findings in the scoped service/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal core snapshot mapping extraction that
preserves API contracts, baseline filtering behavior, freshness behavior, operator workflows, and
public documentation truth.
