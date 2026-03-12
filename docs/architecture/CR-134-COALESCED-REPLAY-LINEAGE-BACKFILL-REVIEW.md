## CR-134 - Coalesced Replay Lineage Backfill Review

### Finding
The durable replay chain preserved correlation lineage when a newly observed impacted date was earlier than the stored one, but it still dropped lineage in one real case: the first coalesced trigger/job row could be created with `correlation_id = NULL`, and a later duplicate for the same impacted date with a real correlation id would not backfill that missing lineage.

That left durable replay state under-audited even though enough information had later arrived to recover the lineage.

### Fix
- `InstrumentReprocessingStateRepository.upsert_state(...)` now backfills `correlation_id` when the stored value is `NULL`, even if the impacted date stays the same.
- `ReprocessingJobRepository.create_job(...)` now does the same for coalesced pending `RESET_WATERMARKS` jobs.
- Added DB-backed proofs for both paths.

### Why it matters
Coalescing should preserve earliest business impact without throwing away better lineage. A same-date duplicate with stronger metadata is not redundant from an audit perspective.

### Evidence
- `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`
