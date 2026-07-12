# CR-226 - Support Overview Oldest Replay Key State Review

Status: Hardened

## Scope
- `ReprocessingHealthSummary`
- `SupportOverviewResponse`
- `ReprocessingSloBucket`
- replay health summary projection in `OperationsRepository` and `OperationsService`

## Problem
The support overview and calculator SLO already exposed the oldest replay security id, but that still hid the actual key state behind the replay backlog summary.

Operators still had to pivot into the replay-key listing to see the oldest key's epoch and freshness, even though those are the next most important fields after the security id.

## Fix
- Extended replay health summary projection with:
  - `oldest_reprocessing_epoch`
  - `oldest_reprocessing_updated_at`
- Surfaced both fields through:
  - `SupportOverviewResponse`
  - `ReprocessingSloBucket`
- Strengthened repository, service, router dependency, and OpenAPI tests to prove the new contract

## Why This Matters
- the replay backlog summary is now closer to the concrete oldest key state
- operators can assess whether the oldest replay key is stale and which epoch it belongs to without an immediate second pivot
- this improves overview-to-detail coherence for replay support surfaces

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
