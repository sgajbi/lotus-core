# SELL Slice 4 - Disposal Policy, Oversell Gates, and Cash Linkage

This slice hardens deterministic disposal behavior and cash-linkage metadata propagation for SELL processing.

## Implemented in this slice

- Added deterministic SELL policy metadata assignment during cost-calculator processing:
  - `SELL_FIFO_POLICY` when portfolio cost basis is FIFO/default
  - `SELL_AVCO_POLICY` when portfolio cost basis is AVCO
  - policy version `1.0.0`
- Enforced strict oversell gate in SELL calculation path:
  - compare requested sell quantity vs available quantity before disposal
  - block oversold quantity under strict policy with deterministic invariant error
  - if `SELL_ALLOW_OVERSOLD_POLICY` is configured, return explicit unsupported-policy invariant error (no silent behavior)
- Preserved/propagated linkage identifiers into persisted and emitted SELL events:
  - `economic_event_id`
  - `linked_transaction_group_id`

## Evidence

- Unit tests:
  - `tests/unit/services/portfolio_transaction_processing_service/transaction/test_booking_metadata.py`
  - `tests/unit/services/portfolio_transaction_processing_service/cost/test_cost_workflow.py`
  - `tests/unit/services/portfolio_transaction_processing_service/cost/test_cost_calculator.py`

## Notes

- This slice focuses on deterministic policy and linkage behavior.
- Full disposal-effect query surfaces remain in subsequent slices.
