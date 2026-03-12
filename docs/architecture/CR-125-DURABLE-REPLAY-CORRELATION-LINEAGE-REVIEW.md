# CR-125 Durable Replay Correlation Lineage Review

## Scope
- `instrument_reprocessing_state`
- `reprocessing_jobs`
- `price_event_consumer`
- `valuation_scheduler`

## Problem
Back-dated price events preserved correlation on the immediate valuation-job path, but lost it on the durable replay path:
- trigger row carried no correlation id
- reset-watermarks job carried no correlation id

That left the replay chain auditable only at the edge, not in durable control tables.

## Fix
- Added nullable `correlation_id` to:
  - `instrument_reprocessing_state`
  - `reprocessing_jobs`
- Trigger upsert now preserves the correlation id associated with the earliest impacted date.
- Scheduler now propagates trigger correlation into the coalesced `RESET_WATERMARKS` job.
- Generic reprocessing jobs can also persist correlation explicitly.

## Proof
- Unit:
  - `tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py`
  - `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
- DB-backed integration:
  - `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
  - `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`
- Migration contract:
  - `f0a1b2c3d4e5_feat_add_replay_correlation_lineage.py`

## Result
Replay lineage is now durable end to end for the back-dated price path:
- market price event
- instrument trigger row
- reset-watermarks durable job
