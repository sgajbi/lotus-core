# CR-094 Position Consumer Replay Boundary Review

## Scope

- `src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py`
- `tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py`

## Finding

`TransactionEventConsumer` supports two distinct paths:

- stage-gate payloads that must hydrate the canonical transaction row
- replay/original transaction payloads that already contain the transaction contract

The consumer already implemented that split, but the tests did not explicitly lock the replay
boundary:

- no canonical lookup on replay payload
- replay epoch preserved as-is
- idempotency recorded directly on the replay payload path

## Change

- Added consumer-level tests proving replay payloads:
  - bypass canonical transaction lookup
  - preserve replay epoch
  - still mark idempotency correctly on the direct replay path

## Result

The consumer boundary between stage-gated canonical lookup and replay-direct processing is now
explicitly protected below integration/E2E.

## Evidence

- `python -m pytest tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py -q`
