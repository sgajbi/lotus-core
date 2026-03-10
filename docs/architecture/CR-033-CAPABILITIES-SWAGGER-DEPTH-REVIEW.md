# CR-033 Capabilities Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the control-plane capabilities endpoint.

## Findings

- The capabilities endpoint already returned a solid shared response DTO.
- The remaining gap was query-parameter depth on the router:
  - `consumer_system` description was still terse and example-free
  - `tenant_id` had no explicit examples
- This was a smaller gap than the other control-plane routers, but it was still below the now-set
  contract standard.

## Actions Taken

- Added explicit examples and tightened query-parameter descriptions on the capabilities route.
- Added an OpenAPI integration assertion covering:
  - `consumer_system` description/default
  - `tenant_id` description/default

## Follow-up

- Continue the review program outside the main control-plane Swagger surfaces:
  - remaining stale historical references
  - any weaker HTTP docs outside `query_control_plane_service`

## Evidence

- `src/services/query_control_plane_service/app/routers/capabilities.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
