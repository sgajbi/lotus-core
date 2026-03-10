# CR-037 Portfolio Discovery Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the top-level portfolio discovery endpoints in
`query_service`:

- `GET /portfolios/`
- `GET /portfolios/{portfolio_id}`

## Findings

- The portfolio discovery endpoints were functionally correct but still under-documented compared
  with the hardened read-plane surfaces.
- The main remaining contract gap was parameter and error-example depth:
  - query filters on portfolio discovery did not carry examples
  - the single-portfolio lookup had no concrete `404` example
  - the single-portfolio route lacked an explicit description
- These are top-level navigation/discovery APIs, so they should be fully self-describing in
  Swagger.

## Actions Taken

- Added explicit descriptions/examples for:
  - `portfolio_id`
  - `client_id`
  - `booking_center_code`
- Added a concrete `404` portfolio-not-found example for `GET /portfolios/{portfolio_id}`.
- Added an OpenAPI integration assertion that locks the richer portfolio discovery contract in
  place.

## Follow-up

- Continue the same depth pass on the remaining `query_service` read-plane endpoints.
- Keep the top-level discovery APIs aligned with the same documentation standard as the narrower
  investigative APIs.

## Evidence

- `src/services/query_service/app/routers/portfolios.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
