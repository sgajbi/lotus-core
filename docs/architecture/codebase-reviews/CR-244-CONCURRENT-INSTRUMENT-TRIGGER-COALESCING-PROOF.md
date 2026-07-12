# CR-244 Concurrent Instrument Trigger Coalescing Proof

## Scope

- Instrument reprocessing trigger upsert
- Concurrent duplicate price-trigger arrivals for the same security

## Finding

The instrument reprocessing trigger repository already used a correct-looking UPSERT shape for one
row per security with earliest-date coalescing and correlation backfill. But that behavior had only
been proved sequentially, not under real concurrent sessions.

## Action Taken

- Added a DB-backed two-session integration test that forces concurrent duplicate arrivals for the
  same security before either session executes the UPSERT
- Proved that the durable state still converges to:
  - one row per security
  - the earliest impacted date
  - the correlation id belonging to the earliest impacted date

## Why This Matters

This closes another unfinished duplicate-arrival contention gap in the replay chain. Price-trigger
coalescing is upstream of durable replay fanout; if it fails under contention, replay correctness
can drift before the worker ever sees the job.

## Evidence

- Test:
  - `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
- Validation:
  - `python -m pytest tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py -q`
  - Result: `6 passed`
  - `python -m ruff check tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`

## Follow-up

- Continue the same contention-proof pattern on valuation job upsert under duplicate scheduler
  pressure.
- After that, move to support/control summary consistency under changing state so the last unfinished
  concurrency bucket becomes narrower and more explicit.
