# CR-035 Positions Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the core read-plane holdings endpoints in `query_service`:

- `GET /portfolios/{portfolio_id}/positions`
- `GET /portfolios/{portfolio_id}/position-history`

## Findings

- Both endpoints already had the correct response models and portfolio-not-found handling.
- The remaining contract gap was parameter and error-example depth:
  - path/query parameters were still thin compared with the now-hardened transaction ledger
  - the shared portfolio-not-found response lacked a concrete example
- These are high-value read-plane endpoints for holdings screens and troubleshooting, so they should
  be fully self-describing in Swagger.

## Actions Taken

- Added explicit descriptions/examples for:
  - `portfolio_id`
  - `security_id`
  - `start_date`
  - `end_date`
  - `as_of_date`
  - `include_projected`
- Added concrete `404` portfolio-not-found examples for both endpoints.
- Added an OpenAPI integration assertion that locks the richer positions and position-history
  contract in place.

## Follow-up

- Continue the same depth pass on the next weakest `query_service` read-plane endpoint.
- Keep using router-level examples for service-owned not-found behavior even when shared response
  DTOs are already strong.

## Evidence

- `src/services/query_service/app/routers/positions.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
