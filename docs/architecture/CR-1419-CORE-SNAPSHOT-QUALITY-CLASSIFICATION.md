# CR-1419 Core Snapshot Quality Classification

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` snapshot freshness to data-quality classification for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned the policy logic that maps snapshot freshness metadata and
baseline row count to source-data `data_quality_status`. The logic is pure classification and does
not need repositories, pricing, FX, simulation, enrichment, response DTO assembly, or service
instance state.

Keeping it inside the broad service made supportability classification harder to test and reuse
independently from the full snapshot composition path.

## Action

Added `core_snapshot_quality.py` with `snapshot_data_quality_status(...)`. The snapshot service now
delegates runtime metadata quality classification to that focused policy function.

## Compatibility

No API behavior change is intended. Current-snapshot, historical-fallback, missing-baseline,
`COMPLETE`, `PARTIAL`, and `UNKNOWN` classification behavior is unchanged. Response DTOs, source
metadata, OpenAPI shape, and error behavior are unchanged.

## Remaining Issue Scope

This is a partial issue #547 slice. Further bounded collaborators are still needed for simulation
projection, projected valuation, section assembly, and enrichment before #547 should be marked
fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_quality.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_quality.py tests\unit\services\query_service\services\test_core_snapshot_quality.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_quality.py tests\unit\services\query_service\services\test_core_snapshot_quality.py tests\unit\services\query_service\services\test_core_snapshot_service.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_quality.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
