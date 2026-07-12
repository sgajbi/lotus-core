# CR-168 Durable Replay Lineage Boundary Normalization Review

## Finding
Durable replay repositories still trusted caller-provided `correlation_id` values verbatim. Earlier slices normalized sentinel lineage (`"<not-set>"`, empty values) at API, consumer, scheduler, and audit boundaries, but the durable repository layer still accepted poisoned lineage if a caller regressed.

## Change
- Normalized `correlation_id` with `normalize_lineage_value(...)` inside:
  - `ReprocessingJobRepository.create_job(...)`
  - `InstrumentReprocessingStateRepository.upsert_state(...)`
- Added lower-level proof that sentinel lineage is persisted as `NULL`, not as a fake string.

## Outcome
Durable replay lineage is now protected at the repository boundary, so persistence no longer depends on every upstream caller remembering to normalize sentinel context.

## Evidence
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
- `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
