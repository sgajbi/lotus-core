# CR-120 Dead Instrument Reprocessing Repository Ownership Review

## Finding

`InstrumentReprocessingStateRepository` still existed in both:

- `valuation_orchestrator_service`
- `position_valuation_calculator`

Only the `valuation_orchestrator_service` copy was live. The
`position_valuation_calculator` copy had no production imports and no owning
runtime path, so it represented dead alternate ownership for an active replay
trigger contract.

## Decision

Keep instrument-level replay trigger ownership singular under
`valuation_orchestrator_service`.

## Change

- Deleted the dead repository copy from
  `position_valuation_calculator/app/repositories/`.
- Kept the live repository under `valuation_orchestrator_service`, where the
  back-dated price-event trigger path actually uses it.

## Why This Is Better

- Future replay-trigger fixes now have one service owner.
- The codebase no longer suggests a fake shared or dual-owned contract.
- This reduces drift risk on a replay-critical path.

## Evidence

- deleted `src/services/calculators/position_valuation_calculator/app/repositories/instrument_reprocessing_state_repository.py`
- live owner remains `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`
