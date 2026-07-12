# CR-039 Lookup Catalog Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the lookup catalog endpoints in `query_service`:

- `GET /lookups/portfolios`
- `GET /lookups/instruments`
- `GET /lookups/currencies`

## Findings

- The lookup endpoints already had the correct response model and business descriptions.
- The remaining gap was parameter example depth:
  - selector/search parameters had descriptions but little or no concrete example guidance
  - defaulted numeric parameters such as `limit` and `instrument_page_limit` lacked explicit examples
- These endpoints are commonly explored from Swagger for selector UX and integration prototyping, so
  they should be self-explanatory at the parameter level.

## Actions Taken

- Added explicit examples for:
  - `client_id`
  - `booking_center_code`
  - `q`
  - `limit`
  - `product_type`
  - `instrument_page_limit`
  - `source`
- Added an OpenAPI integration assertion that locks the richer lookup-catalog contract in place.

## Follow-up

- Continue the same depth pass on any remaining weaker `query_service` read/reference endpoints.
- Keep the lighter-weight lookup/read endpoints at the same documentation standard as the heavier
  portfolio and transaction surfaces.

## Evidence

- `src/services/query_service/app/routers/lookups.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
