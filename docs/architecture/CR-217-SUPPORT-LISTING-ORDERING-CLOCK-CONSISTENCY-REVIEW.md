# CR-217 - Support Listing Ordering Clock Consistency Review

Status: Hardened

## Scope
- support listing repository queries
- valuation, aggregation, analytics export, replay key, and replay job support listings

## Problem
After `CR-216`, support listing stale-state labels honored the caller-selected stale threshold in the service layer, but the repository listing queries still computed stale ordering priority using their own internal `datetime.now(...)` clock.

That meant one response could still be internally inconsistent:
- row ordering driven by one implicit stale cutoff
- row labels driven by a different captured response timestamp

## Fix
- Added `reference_now` to the repository list queries for:
  - valuation jobs
  - aggregation jobs
  - analytics export jobs
  - replay keys
  - replay jobs
- Wired each support listing to pass its captured `generated_at_utc` into the repository query as well as the service-layer classifier
- Strengthened service tests to prove the shared clock is forwarded to the repository list queries
- Added repository SQL tests that prove the ordering cutoff uses the expected `reference_now`

## Why This Matters
- support listing ordering and stale-state labels now derive from one consistent clock
- operators will not see rows prioritized as stale under one hidden cutoff and labeled under another
- this removes another subtle but real trust gap from the operator support plane

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
