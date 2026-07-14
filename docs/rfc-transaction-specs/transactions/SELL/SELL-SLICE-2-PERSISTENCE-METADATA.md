# SELL Slice 2 - Persistence, Linkage, and Policy Metadata

This slice hardens SELL metadata persistence preconditions by ensuring deterministic linkage and policy metadata are present before cost processing and persistence.

## Implemented in this slice

- Added SELL metadata enrichment utility:
  - `enrich_sell_transaction_metadata(...)`
  - deterministic defaults:
    - `economic_event_id = EVT-SELL-<portfolio_id>-<transaction_id>`
    - `linked_transaction_group_id = LTG-SELL-<portfolio_id>-<transaction_id>`
    - `calculation_policy_id = SELL_DEFAULT_POLICY`
    - `calculation_policy_version = 1.0.0`
- Preserved upstream-provided metadata when already supplied.
- Integrated enrichment in cost-calculator consumer before engine transformation/persistence.

## Evidence

- Unit tests:
  - `tests/unit/services/portfolio_transaction_processing_service/transaction/test_booking_metadata.py`
  - `tests/unit/services/portfolio_transaction_processing_service/application/cost_basis_processing/test_execution.py`
- Consumer integration assertion verifies SELL metadata is present on persisted transaction update payload.

## Notes

- This slice uses additive enrichment and does not require schema changes because required fields already exist in transaction and event models.
