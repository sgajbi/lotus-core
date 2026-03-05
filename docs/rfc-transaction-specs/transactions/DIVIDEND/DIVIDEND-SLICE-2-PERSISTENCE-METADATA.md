# DIVIDEND Slice 2 - Persistence, Linkage, and Policy Metadata

This slice hardens DIVIDEND metadata persistence preconditions by ensuring deterministic linkage and policy metadata are present before cost processing and persistence.

## Implemented in this slice

- Added DIVIDEND metadata enrichment utility:
  - `enrich_dividend_transaction_metadata(...)`
  - deterministic defaults:
    - `economic_event_id = EVT-DIVIDEND-<portfolio_id>-<transaction_id>`
    - `linked_transaction_group_id = LTG-DIVIDEND-<portfolio_id>-<transaction_id>`
    - `calculation_policy_id = DIVIDEND_DEFAULT_POLICY`
    - `calculation_policy_version = 1.0.0`
- Preserved upstream-provided metadata when already supplied.
- Integrated enrichment in cost-calculator consumer before engine transformation/persistence.

## Evidence

- Unit tests:
  - `tests/unit/libs/portfolio_common/test_dividend_linkage.py`
  - `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- Consumer integration assertion verifies DIVIDEND metadata is present on persisted transaction update payload and outbox payload.

## Notes

- This slice uses additive enrichment and does not require schema changes because required fields already exist in transaction and event models.
