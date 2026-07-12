# CR-030 Simulation Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the control-plane Swagger/OpenAPI contract for simulation endpoints.

## Findings

- `query_control_plane_service` simulation endpoints already existed and were functionally correct.
- Their OpenAPI surface was still thin compared with the operations and reconciliation routers:
  - path parameters were undocumented
  - `404` / invalid-state responses had no concrete examples
  - shared simulation DTOs had minimal field-level descriptions and examples
- The baseline gate passed, but the contract was not yet operator-grade.

## Actions Taken

- Added richer field-level descriptions and examples to the shared simulation DTOs in
  `src/services/query_service/app/dtos/simulation_dto.py`.
- Added path parameter descriptions/examples and explicit response examples for the simulation
  control-plane routes in
  `src/services/query_control_plane_service/app/routers/simulation.py`.
- Added an OpenAPI integration assertion covering:
  - `session_id` parameter docs
  - `change_id` parameter docs
  - not-found example shape
  - `SimulationSessionCreateRequest.portfolio_id` schema description

## Follow-up

- Continue the same depth pass on the next weakest active HTTP surface.
- Prefer shared DTO enrichment where the schema is truly shared, but keep router-specific response
  examples local to the owning service.

## Evidence

- `src/services/query_service/app/dtos/simulation_dto.py`
- `src/services/query_control_plane_service/app/routers/simulation.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
