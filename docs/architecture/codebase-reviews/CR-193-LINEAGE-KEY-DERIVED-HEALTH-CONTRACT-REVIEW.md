# CR-193 Lineage Key Derived Health Contract Review

## Finding

CR-192 made lineage-key listings richer, but operators still had to compare raw artifact dates and valuation status by hand to decide whether a key was healthy, replaying, artifact-lagged, or valuation-blocked.

## Change

- Added server-owned derived fields to `LineageKeyRecord`:
  - `has_artifact_gap`
  - `operational_state`
- Centralized the derivation in `OperationsService` so clients do not need to reimplement lineage-health policy.
- Added unit, router, and OpenAPI proof.

## Why it matters

The lineage listing now speaks operator language instead of exposing only raw timestamps. This reduces client duplication, makes support tools simpler, and keeps lineage triage policy owned in one place.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
