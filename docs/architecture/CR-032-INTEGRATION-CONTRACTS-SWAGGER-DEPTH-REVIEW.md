# CR-032 Integration Contracts Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the general integration endpoints in
`query_control_plane_service`.

## Findings

- The integration router already had the right endpoint set and strong shared DTO coverage.
- The main remaining contract gap was router-level documentation on the highest-value control-plane
  endpoints:
  - policy resolution query parameters
  - core snapshot path/query parameters
  - service-owned error responses for policy block, not found, conflict, and unavailable states
  - invalid enrichment-bulk payload example
- The baseline gates passed, but the contract was still thinner than the now-hardened simulation,
  operations, analytics-inputs, and reconciliation surfaces.

## Actions Taken

- Added query parameter descriptions/examples for `consumer_system`, `tenant_id`, and
  `include_sections` on the effective-policy endpoint.
- Added path/query parameter descriptions/examples for the core-snapshot endpoint.
- Added concrete response examples for:
  - policy-blocked requests
  - core-snapshot not found
  - core-snapshot conflict
  - unavailable section due to valuation dependency gaps
  - invalid instrument enrichment request
- Added an OpenAPI integration assertion covering those parameter and response examples.

## Follow-up

- Continue the same depth pass on remaining integration/reference routers where operation text still
  carries more meaning than explicit path/response contracts.

## Evidence

- `src/services/query_control_plane_service/app/routers/integration.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
