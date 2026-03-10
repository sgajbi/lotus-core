# CR-052 Benchmark And Reference Integration Swagger Review

## Scope
- Benchmark assignment, benchmark definition, benchmark market-series, index-series, and coverage endpoints in the integration control-plane router

## Findings
- The integration router had already been hardened for policy and core-snapshot endpoints.
- The lower benchmark/reference endpoints still lacked explicit path parameter examples and concrete 404 examples for the benchmark assignment/definition cases.
- That made the reference-data portion of the contract weaker than the already-hardened integration surface.

## Actions Taken
- Added path parameter descriptions/examples for:
  - `portfolio_id`
  - `benchmark_id`
  - `index_id`
- Added explicit 404 response examples for:
  - portfolio benchmark assignment not found
  - benchmark definition not found
- Added OpenAPI integration assertions to lock those parameter and error contracts in place.

## Follow-up
- Continue the Swagger-depth pass on the next weakest active integration/reference endpoint surface.

## Evidence
- `src/services/query_control_plane_service/app/routers/integration.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
