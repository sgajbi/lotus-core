## CR-117: Reset-watermarks durable job coalescing

### Scope
- durable reprocessing job queue for `RESET_WATERMARKS`

### Finding
Repeated instrument-level reprocessing triggers for the same security could create multiple pending `RESET_WATERMARKS` jobs even before the worker claimed the first one. That inflated the durable queue with redundant work and weakened recovery determinism.

### Change
- `ReprocessingJobRepository.create_job(...)` now coalesces pending `RESET_WATERMARKS` jobs by `security_id`.
- If a newer request carries an earlier impacted date, the existing pending job is updated to the earlier date instead of creating a duplicate job.
- Added unit coverage for both same/later-date coalescing and earlier-date merge behavior.

### Follow-up
If duplicate fanout pressure still shows up under production load, consider a database-level uniqueness contract for pending reset-watermarks jobs keyed by `(job_type, payload->>security_id)` rather than relying only on repository behavior.

### Evidence
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
- `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py -q`
