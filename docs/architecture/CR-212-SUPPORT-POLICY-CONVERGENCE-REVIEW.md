# CR-212 - Support Policy Convergence Review

Status: Hardened

## Scope
- support policy defaults and descriptions for stale thresholds and failed windows
- `operations.py` router
- `OperationsService`
- support DTO contracts

## Problem
Support-policy defaults and descriptions were duplicated across:
- router query parameter declarations
- service method defaults
- DTO field descriptions

That made the support plane drift-prone:
- one endpoint could change a default while another stayed behind
- query parameter descriptions could diverge from response-field semantics
- stale/failure policy corrections required touching several places by hand

## Fix
- Added shared `support_policy.py` for:
  - default stale threshold minutes
  - default failed window hours
  - shared support policy descriptions
- Switched router query params, service defaults, and DTO descriptions to reuse the shared policy constants
- Re-ran support-plane unit, router dependency, and OpenAPI tests

## Why This Matters
- support policy is now defined once instead of repeated across layers
- future policy changes are less likely to create hidden API/runtime drift
- this is a real maintainability and governance improvement, not cosmetic cleanup

## Evidence
- `src/services/query_service/app/support_policy.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
