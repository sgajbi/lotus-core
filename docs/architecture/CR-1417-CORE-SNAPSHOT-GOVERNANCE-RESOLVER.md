# CR-1417 Core Snapshot Governance Resolver

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` governance context and policy resolution for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned the data structures and logic that translate query-control-plane
governance context into snapshot response governance metadata. The logic is pure policy-context
mapping and does not need repository, pricing, FX, projection, or response assembly dependencies.

Keeping it inside the broad service made governance behavior harder to test independently from full
snapshot response assembly.

## Action

Added `core_snapshot_governance.py` with `SnapshotGovernanceContext`,
`CoreSnapshotGovernanceResolution`, and `resolve_core_snapshot_governance(...)`. The snapshot
service now delegates governance mapping to this module while preserving its public
`get_core_snapshot(...)` contract. Query-control-plane routers import the governance context from
the governance module instead of the broad service module.

## Compatibility

No API behavior change is intended. Request sections, applied/dropped section propagation, default
inline policy metadata, strict-mode propagation, warnings, consumer system, tenant id, response DTOs,
OpenAPI shape, and error behavior are unchanged.

## Remaining Issue Scope

This is a partial issue #547 slice. Further bounded collaborators are still needed for simulation
projection, projected valuation, section assembly, and instrument enrichment before #547 should be
marked fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_governance.py tests\unit\services\query_service\services\test_core_snapshot_service.py tests\unit\services\query_control_plane_service\routers\test_integration_router.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_governance.py src\services\query_control_plane_service\app\routers\integration.py tests\unit\services\query_service\services\test_core_snapshot_governance.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_governance.py src\services\query_control_plane_service\app\routers\integration.py tests\unit\services\query_service\services\test_core_snapshot_governance.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_governance.py src\services\query_control_plane_service\app\routers\integration.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
