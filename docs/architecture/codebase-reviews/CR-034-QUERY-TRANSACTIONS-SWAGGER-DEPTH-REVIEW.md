# CR-034 Query Transactions Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the Swagger/OpenAPI contract for the core read-plane transaction ledger endpoint in
`query_service`.

## Findings

- The transaction ledger endpoint was functionally complete and already exposed the right FX-aware
  filter set.
- The remaining contract gap was parameter and error-example depth:
  - path/query parameters were not documented to the same standard as the hardened control-plane
    surfaces
  - the `404 portfolio not found` response lacked a concrete example
- This mattered because the transaction ledger is one of the main investigative read APIs and now
  carries FX-specific filter semantics that should be discoverable directly in Swagger.

## Actions Taken

- Added explicit descriptions/examples for:
  - `portfolio_id`
  - `security_id`
  - `transaction_type`
  - `component_type`
  - `linked_transaction_group_id`
  - `fx_contract_id`
  - `swap_event_id`
  - `near_leg_group_id`
  - `far_leg_group_id`
  - `start_date`
  - `end_date`
  - `as_of_date`
  - `include_projected`
- Added a concrete `404` example for portfolio-not-found.
- Added an OpenAPI integration assertion that locks the richer parameter and error contract in
  place.

## Follow-up

- Continue the same depth pass on the next weakest `query_service` read-plane endpoint.
- Prefer explicit router-level examples for service-owned behavior even when shared DTO coverage is
  already strong.

## Evidence

- `src/services/query_service/app/routers/transactions.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
