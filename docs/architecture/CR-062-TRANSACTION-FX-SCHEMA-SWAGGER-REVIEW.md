# CR-062 Transaction FX Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/transaction_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- After CR-060 and CR-061, the transaction core, dual-leg, and income fields were in good shape, but the FX-specific field family still used thinner wording.
- This is an active contract surface for:
  - FX spot, forward, and swap ingestion
  - contract lifecycle linkage
  - settlement-leg classification
  - realized FX P&L population semantics

## Actions taken

- Tightened field-level descriptions for:
  - `component_type`
  - `fx_cash_leg_role`
  - `settlement_status`
  - `fx_rate_quote_convention`
  - `contract_rate`
  - `fx_contract_id`
  - `settlement_of_fx_contract_id`
  - `swap_event_id`
  - `near_leg_group_id`
  - `far_leg_group_id`
  - `spot_exposure_model`
  - `fx_realized_pnl_mode`
  - `realized_capital_pnl_local`
  - `realized_fx_pnl_local`
  - `realized_total_pnl_local`
  - `realized_capital_pnl_base`
  - `realized_fx_pnl_base`
  - `realized_total_pnl_base`
- Added ingestion app OpenAPI assertions to lock the richer FX schema behavior in place.

## Result

- The FX-specific transaction fields now read as first-class canonical ingestion contracts rather than a thin specialist appendix to the generic transaction schema.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
