# CR-271 Valuation Consumer Ownership-Loss Proof

## Summary

The valuation consumer already fenced terminal side effects behind `update_job_status(...)`, but we
still lacked DB-backed proof that a late ownership loss would suppress durable snapshot, outbox, and
idempotency writes.

## Finding

- Class: concurrency correctness risk
- Consequence: without an integration proof, the valuation consumer still relied on unit-level
  confidence for a banking-grade guarantee that a late worker does not publish durable completion
  side effects after ownership is lost.

## Action Taken

- added a DB-backed ownership-loss proof in
  `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_consumer_persistence.py`
- used a second database session to mark the same valuation job `COMPLETE` immediately before the
  real repository `update_job_status(...)` executes
- proved that the consumer then:
  - writes no `DailyPositionSnapshot`
  - emits no outbox completion event
  - marks no idempotency record
  - leaves the durable job row completed by the competing owner

## Evidence

- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_consumer_persistence.py -q`
  - `2 passed`
- `python -m ruff check tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_consumer_persistence.py`
  - passed

## Follow-up

- keep pushing terminal ownership-loss guarantees down into DB-backed proofs for any remaining
  worker consumer that can publish durable side effects after status transitions
