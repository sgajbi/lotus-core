# CR-123 Instrument Trigger Coalescing DB Proof

## Finding

The live `InstrumentReprocessingStateRepository` is the durable source of
instrument-level replay triggers, but the coalescing behavior had not been
proven against the real database path. Without that proof, repeated back-dated
price events could still regress into multiple rows or widened impacted dates
without being caught below scheduler/E2E level.

## Decision

Add DB-backed proof that repeated upserts leave one trigger row per security and
preserve the earliest impacted date.

## Change

- Added integration coverage for the live
  `valuation_orchestrator_service` trigger repository.
- Also corrected the stale module header so the file reflects its real owner
  path.

## Why This Is Better

- Locks the trigger-source contract below the scheduler layer.
- Ensures repeated back-dated price events collapse to one durable replay
  trigger per security.
- Reduces the chance of replay drift being discovered only in heavy E2E runs.

## Evidence

- `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`
- `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
