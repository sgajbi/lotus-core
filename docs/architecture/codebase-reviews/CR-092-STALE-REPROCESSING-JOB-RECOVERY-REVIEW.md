# CR-092 Stale Reprocessing Job Recovery Review

## Scope

- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`

## Finding

`reprocessing_jobs` already tracked:

- `status`
- `attempt_count`
- `last_attempted_at`
- `updated_at`

But unlike valuation and aggregation jobs, there was no stale-processing recovery path.

If `ReprocessingWorker` died after claiming jobs and before terminal status update, those rows could
stay in `PROCESSING` indefinitely and never re-enter the queue.

## Change

- Added `ReprocessingJobRepository.find_and_reset_stale_jobs(timeout_minutes=15)`
- Wired `ReprocessingWorker` to reset stale `PROCESSING` jobs before attempting the next claim batch
- Added unit coverage for:
  - stale reset query/update behavior
  - noop behavior when nothing is stale
  - worker ordering: stale reset runs before claim

## Result

Durable reprocessing jobs now have the same bounded recovery property as the other durable job
queues. A worker crash can no longer leave `RESET_WATERMARKS` jobs stuck forever in
`PROCESSING`.

## Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py -q`
