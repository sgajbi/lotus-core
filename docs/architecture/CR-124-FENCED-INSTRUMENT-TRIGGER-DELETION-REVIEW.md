# CR-124 Fenced Instrument Trigger Deletion Review

## Finding

`ValuationScheduler` converted fetched instrument-level replay triggers into
durable `RESET_WATERMARKS` jobs and then deleted trigger rows by `security_id`
only. That created a race: if a newer back-dated price event lowered the
`earliest_impacted_date` for the same security between fetch and delete, the
older scheduler cycle could delete the newer replay requirement and lose work.

## Decision

Fence trigger deletion by the fetched trigger state, not just `security_id`.

## Change

- `delete_instrument_reprocessing_triggers(...)` now deletes by
  `(security_id, earliest_impacted_date)` pairs.
- `ValuationScheduler._process_instrument_level_triggers(...)` now passes the
  fetched trigger fences instead of raw security ids.
- Added DB-backed proof that a stale delete cannot remove a trigger row whose
  impacted date was lowered after fetch.

## Why This Is Better

- Prevents lost replay work under concurrent back-dated price events.
- Keeps the durable trigger source monotonic: newer earlier-date requirements
  survive older scheduler cycles.
- Pushes the race proof below the scheduler/E2E layer.

## Evidence

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`
