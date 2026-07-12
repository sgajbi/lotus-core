# CR-194 Lineage Detail Derived Health Alignment Review

## Finding

CR-193 strengthened the lineage-key listing, but the per-key lineage detail still exposed only raw artifact fields. Drilling into the detail view meant losing the same server-owned health semantics the list already provided.

## Change

- Added `has_artifact_gap` and `operational_state` to `LineageResponse`.
- Reused the same service-owned derivation already introduced for lineage-key listings.
- Added unit, router, and OpenAPI proof.

## Why it matters

The lineage detail and lineage list now speak the same operator-facing language. Support tools and humans can drill from list to detail without crossing a semantic boundary and re-deriving health logic by hand.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
