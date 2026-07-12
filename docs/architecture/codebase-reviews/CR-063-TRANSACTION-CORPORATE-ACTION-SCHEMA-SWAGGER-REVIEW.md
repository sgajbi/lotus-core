# CR-063 Transaction Corporate Action Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/transaction_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- After CR-060 through CR-062, the transaction core, dual-leg, income, and FX field families were materially stronger.
- The remaining specialist weakness in `transaction_dto.py` was the corporate-action and synthetic-flow tail.
- This is still an active contract surface for:
  - parent/child corporate-action linkage
  - transfer and cash-in-lieu settlement relationships
  - position-level synthetic flow analytics

## Actions taken

- Tightened field-level descriptions for:
  - `parent_transaction_reference`
  - `linked_parent_event_id`
  - `parent_event_reference`
  - `child_role`
  - `child_sequence_hint`
  - `dependency_reference_ids`
  - `source_instrument_id`
  - `target_instrument_id`
  - `source_transaction_reference`
  - `target_transaction_reference`
  - `linked_cash_transaction_id`
  - `has_synthetic_flow`
  - `synthetic_flow_effective_date`
  - `synthetic_flow_amount_local`
  - `synthetic_flow_currency`
  - `synthetic_flow_amount_base`
  - `synthetic_flow_fx_rate_to_base`
  - `synthetic_flow_price_used`
  - `synthetic_flow_quantity_used`
  - `synthetic_flow_valuation_method`
  - `synthetic_flow_classification`
  - `synthetic_flow_price_source`
  - `synthetic_flow_fx_source`
  - `synthetic_flow_source`
- Added ingestion app OpenAPI assertions to lock the richer corporate-action and synthetic-flow schema behavior in place.

## Result

- The corporate-action and synthetic-flow tail now reads as a first-class canonical ingestion contract rather than a weak specialist appendix at the end of the transaction schema.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
