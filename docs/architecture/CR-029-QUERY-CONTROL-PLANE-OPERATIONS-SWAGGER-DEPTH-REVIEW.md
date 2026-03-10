# CR-029 Query Control Plane Operations Swagger Depth Review

## Scope

Raise the operational support and lineage endpoints in
`query_control_plane_service` from baseline OpenAPI compliance to stronger
operator-grade Swagger quality.

## Finding

The operations router already documented the endpoint purpose well, but the
parameter and error-path depth was still uneven:

- portfolio and security path identifiers lacked concrete examples
- filter/query parameters had descriptions but not enough concrete examples
- 404 response behavior existed in runtime but was not documented with payload
  examples

## Action Taken

1. Added explicit examples for portfolio/security path identifiers.
2. Added explicit examples on the main operational query filters and pagination
   parameters.
3. Added 404 response examples for the portfolio-not-found and lineage-not-found
   cases.
4. Added an OpenAPI integration test that asserts these parameter and error
   examples are present.

## Result

The support/lineage control-plane APIs now document:

- what identifiers look like
- how the main filters are expected to be used
- what the not-found error payloads look like

## Evidence

- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
