# CR-157 Coalesced Replay Lineage Null Earlier-Date Review

## Scope

- Durable replay trigger coalescing
- Durable `RESET_WATERMARKS` job coalescing
- Banking-grade replay lineage preservation

## Finding

Both coalescing paths treated an earlier impacted date as authoritative for
`correlation_id` even when the incoming earlier event had `correlation_id = NULL`.

That meant a later event with valid lineage could be erased by an older event that
carried no lineage at all:

- `instrument_reprocessing_state`
- pending `RESET_WATERMARKS` rows in `reprocessing_jobs`

This is a real audit-quality defect. Earliest business impact should win for date
selection, but missing lineage should not destroy already-known lineage.

## Fix

- `InstrumentReprocessingStateRepository.upsert_state(...)`
  - preserve existing non-null `correlation_id` when an earlier incoming row has
    `correlation_id = NULL`
- `ReprocessingJobRepository.create_job(...)`
  - preserve existing non-null `correlation_id` when an earlier coalesced
    `RESET_WATERMARKS` job arrives with `correlation_id = NULL`

## Evidence

- `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`

## Validation

- DB-backed replay lineage slice:
  - `10 passed`
- touched-surface `ruff check`:
  - passed

## Follow-up

- Keep earliest impacted date and durable lineage as separate concerns:
  - earlier business impact should win date ordering
  - better existing lineage should not be erased by missing lineage
