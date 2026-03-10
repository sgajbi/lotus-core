# CR-061 Transaction Dual-Leg and Income Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/transaction_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- After CR-060, the transaction core ledger fields were stronger, but the dual-leg and income-related field family still used older wording and weaker schema-level descriptions.
- This is an active business surface:
  - linked product/cash legs
  - adjustment-style linkage
  - interest deductions and net reconciliation

## Actions taken

- Tightened field-level descriptions for:
  - `economic_event_id`
  - `linked_transaction_group_id`
  - `calculation_policy_id`
  - `calculation_policy_version`
  - `cash_entry_mode`
  - `external_cash_transaction_id`
  - `settlement_cash_account_id`
  - `settlement_cash_instrument_id`
  - `movement_direction`
  - `originating_transaction_id`
  - `originating_transaction_type`
  - `adjustment_reason`
  - `link_type`
  - `reconciliation_key`
  - `interest_direction`
  - `withholding_tax_amount`
  - `other_interest_deductions_amount`
  - `net_interest_amount`
- Added ingestion app OpenAPI assertions to lock the richer schema behavior in place

## Result

- The dual-leg and income semantics in the transaction schema now read as first-class canonical contracts rather than legacy compatibility fields.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
