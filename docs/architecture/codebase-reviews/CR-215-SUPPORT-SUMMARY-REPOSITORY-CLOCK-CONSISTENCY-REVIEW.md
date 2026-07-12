# CR-215 - Support Summary Repository Clock Consistency Review

Status: Hardened

## Scope
- `OperationsRepository` health summary queries
- `OperationsService.get_support_overview(...)`
- `OperationsService.get_calculator_slos(...)`

## Problem
The support overview and calculator SLO responses captured one `generated_at_utc` timestamp in the service layer, but the repository health summary queries still computed stale and failed cutoffs using their own internal `datetime.now(...)` calls.

That meant one operator-facing snapshot could still be assembled from multiple drifting time windows underneath it.

## Fix
- Added `reference_now` to repository health summary methods for:
  - replay health
  - valuation job health
  - aggregation job health
  - analytics export job health
- Wired `generated_at_utc` from `OperationsService` through to those repository methods
- Strengthened service-level tests to prove the shared clock is forwarded
- Added repository-level tests that prove the generated SQL uses the exact expected stale and failed cutoffs from the supplied reference timestamp

## Why This Matters
- support overview and calculator SLO snapshots are now temporally consistent end to end
- stale and recent-failure classifications no longer depend on multiple hidden repository clock reads
- this removes a subtle but real trust gap from operator-facing support summaries

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
