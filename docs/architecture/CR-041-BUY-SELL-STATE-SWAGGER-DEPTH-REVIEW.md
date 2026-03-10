# CR-041 BUY/SELL State Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the investigative BUY/SELL state endpoints in
`query_service`.

Reviewed routes:

- `GET /portfolios/{portfolio_id}/positions/{security_id}/lots`
- `GET /portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets`
- `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage`
- `GET /portfolios/{portfolio_id}/positions/{security_id}/sell-disposals`
- `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage`

## Findings

- These routes already had useful summaries and business descriptions.
- The remaining gap was path/error contract depth:
  - path parameters had no descriptions/examples
  - not-found states lacked concrete examples
- These endpoints are used for audit and reconciliation investigations, so explicit not-found
  semantics matter in Swagger.

## Actions Taken

- Added explicit path parameter descriptions/examples for:
  - `portfolio_id`
  - `security_id`
  - `transaction_id`
- Added concrete `404` examples for BUY-state, SELL-state, and cash-linkage not-found cases.
- Added an OpenAPI integration assertion that locks the richer investigative state contract in
  place.

## Follow-up

- Continue the same depth pass on any remaining thinner API surfaces.
- Preserve the pattern of concrete not-found examples on investigative read endpoints.

## Evidence

- `src/services/query_service/app/routers/buy_state.py`
- `src/services/query_service/app/routers/sell_state.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
