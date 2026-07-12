# CR-270 Concurrent Trigger Claim Proof

## Summary

Instrument reprocessing trigger coalescing was already DB-backed, but the trigger claim path itself
still lacked proof that two workers racing to claim the same trigger batch could not both take the
same durable state row.

## Finding

- Class: concurrency correctness risk
- Consequence: replay-trigger ingestion had coalescing evidence, but not worker-claim evidence,
  leaving a real gap in the trigger lifecycle under concurrent orchestrator workers.

## Action Taken

- added a DB-backed two-session contention proof in
  `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
- proved that two concurrent `claim_instrument_reprocessing_triggers(batch_size=1)` calls against
  one trigger row converge to:
  - exactly one claimed trigger returned across both workers
  - the durable trigger row deleted exactly once

## Evidence

- `python -m pytest tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py -q`
  - `7 passed`
- `python -m ruff check tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
  - passed

## Follow-up

- keep reviewing remaining claim/update control paths for the same pattern: if a worker claims
  durable state with `SKIP LOCKED` or similar queue mechanics, prove the no-double-claim invariant
