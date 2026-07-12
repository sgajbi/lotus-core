# CR-036 Cashflow Projection Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the core read-plane cashflow projection endpoint in
`query_service`.

## Findings

- The endpoint already had the correct response model and business description.
- The remaining contract gap was router-level parameter and error-example depth:
  - `portfolio_id`, `horizon_days`, `as_of_date`, and `include_projected` lacked explicit examples
  - the portfolio-not-found response had no concrete example
- This endpoint is used for operational liquidity planning, so those controls should be directly
  visible in Swagger.

## Actions Taken

- Added explicit descriptions/examples for:
  - `portfolio_id`
  - `horizon_days`
  - `as_of_date`
  - `include_projected`
- Added a concrete `404` portfolio-not-found example.
- Added an OpenAPI integration assertion that locks the richer contract in place.

## Follow-up

- Continue the same depth pass on the remaining `query_service` read-plane endpoints.
- Prefer concrete router-level examples for service-owned not-found behavior.

## Evidence

- `src/services/query_service/app/routers/cashflow_projection.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
