# CR-050 Simulation Shared Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared simulation DTO schemas used by `query_control_plane_service` simulation endpoints.

Reviewed schemas:

- `SimulationSessionResponse`
- `SimulationChangesResponse`
- `ProjectedPositionsResponse`

## Findings

The simulation router already had good parameter and error documentation after CR-030, but the
reusable session, change-list, and projected-position component schemas still relied mostly on field
text without concrete nested examples.

## Actions Taken

- Added schema-level nested examples for session metadata, change lists, and projected positions.
- Added an OpenAPI integration assertion that locks these richer component-schema descriptions in
  place.

## Follow-up

Continue the same schema-depth pass on the next weakest shared DTO surface.

## Evidence

- `src/services/query_service/app/dtos/simulation_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
