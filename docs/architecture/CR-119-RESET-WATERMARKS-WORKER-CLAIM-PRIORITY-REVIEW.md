# CR-119 Reset-Watermarks Worker Claim Priority Review

## Finding

`ReprocessingJobRepository.find_and_claim_jobs(...)` claimed all job types by
`created_at` only. After CR-118, instrument-level triggers were already being
prioritized by the oldest `earliest_impacted_date`, but the durable
`RESET_WATERMARKS` queue still consumed work by row creation order.

That left the replay pipeline with inconsistent priority:

- trigger table: oldest-impact-first
- durable worker queue: oldest-row-first

Under backlog, that weakens recovery quality and makes durable replay ordering
depend on incidental enqueue timing.

## Decision

For `RESET_WATERMARKS` jobs, claim work in oldest-impact-first order.

## Change

- `find_and_claim_jobs(...)` now uses job-type-specific ordering:
  - `RESET_WATERMARKS`:
    - `(payload->>'earliest_impacted_date')::date ASC`
    - `created_at ASC`
    - `id ASC`
  - all other job types:
    - `created_at ASC`
    - `id ASC`
- Added repository tests that lock both branches of the query contract.

## Why This Is Better

- Durable worker execution now matches upstream trigger priority.
- Recovery starts with the oldest business impact first, not whichever row was
  inserted first.
- The contract is deterministic and explicit.

## Evidence

- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
