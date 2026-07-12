# CR-1416 Core Snapshot Delivery Dependency Boundary

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` delivery dependency wiring for GitHub issue #547.

## Finding

`CoreSnapshotService` still imported FastAPI `Depends` and the shared async DB-session dependency
to expose `get_core_snapshot_service` from the service module. That coupled a core snapshot
composition service to HTTP delivery wiring even though the query-control-plane already has a
dedicated dependency module.

## Action

Removed FastAPI dependency wiring from `core_snapshot_service.py`. The existing
`query_control_plane_service.app.dependencies.get_core_snapshot_service` remains the delivery-layer
factory and constructs the service through `CoreSnapshotDependencies.from_session`.

## Compatibility

No API behavior change is intended. Query-control-plane routers already import
`get_core_snapshot_service` from the control-plane dependency module. Existing service construction,
repository dependency creation, request handling, response DTOs, source metadata, errors, and
runtime behavior are unchanged.

## Remaining Issue Scope

This is a partial issue #547 slice. Further bounded collaborators are still needed for simulation
projection, projected valuation, section assembly, governance resolution, and instrument enrichment
before #547 should be marked fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change moves internal dependency wiring and does
not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py tests\unit\services\query_control_plane_service\routers\test_integration_router.py tests\integration\services\query_control_plane_service\test_integration_router_dependency.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_control_plane_service\app\dependencies.py tests\unit\services\query_service\services\test_core_snapshot_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_control_plane_service\app\dependencies.py tests\unit\services\query_service\services\test_core_snapshot_service.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_control_plane_service\app\dependencies.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
