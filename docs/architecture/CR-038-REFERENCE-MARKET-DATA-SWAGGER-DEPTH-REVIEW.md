# CR-038 Reference Market Data Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the market-data read endpoints in `query_service`:

- `GET /prices/`
- `GET /fx-rates/`

## Findings

- Both endpoints already exposed the correct response models and business descriptions.
- The remaining gap was parameter depth:
  - `security_id`, `from_currency`, and `to_currency` lacked examples and richer wording
  - the optional date-range filters did not provide explicit examples
- These are diagnostic/reference endpoints that should be directly usable from Swagger without
  guessing valid input formats.

## Actions Taken

- Added explicit descriptions/examples for:
  - `security_id`
  - `from_currency`
  - `to_currency`
  - `start_date`
  - `end_date`
- Added an OpenAPI integration assertion that locks the richer contract in place.

## Follow-up

- Continue the same depth pass on the remaining weaker `query_service` reference/read endpoints.
- Keep the reference endpoints aligned with the same example quality as the portfolio and
  transaction read surfaces.

## Evidence

- `src/services/query_service/app/routers/prices.py`
- `src/services/query_service/app/routers/fx_rates.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
