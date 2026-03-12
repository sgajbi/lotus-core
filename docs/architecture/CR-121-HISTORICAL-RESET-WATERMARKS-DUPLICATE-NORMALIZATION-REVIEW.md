# CR-121 Historical Reset-Watermarks Duplicate Normalization Review

## Finding

CR-117 stopped new duplicate pending `RESET_WATERMARKS` jobs from being created
through the repository, but historical duplicates could still already exist in
the durable queue. If left untouched, the worker would eventually process those
rows redundantly even though they all represented the same security-level replay
intent.

## Decision

Normalize the pending `RESET_WATERMARKS` queue before claim so one pending job
remains per `security_id`, carrying the earliest impacted date.

## Change

- Added `normalize_pending_reset_watermarks_duplicates()` to
  `ReprocessingJobRepository`.
- The method:
  - keeps one pending row per `security_id`
  - updates the keeper row to the minimum impacted date
  - deletes the remaining redundant pending rows
- `find_and_claim_jobs("RESET_WATERMARKS", ...)` now runs this normalization
  before the claim query.

## Why This Is Better

- Historical queue residue is cleaned at the durable boundary instead of being
  replayed later as redundant work.
- Worker execution remains aligned to one security-level replay intent.
- The durable queue now self-heals old duplicate state without requiring manual
  intervention.

## Evidence

- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
