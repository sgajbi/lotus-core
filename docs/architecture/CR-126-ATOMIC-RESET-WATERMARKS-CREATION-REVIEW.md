# CR-126 Atomic Reset-Watermarks Creation Review

## Finding

CR-125 moved pending `RESET_WATERMARKS` uniqueness into the database, but
`ReprocessingJobRepository.create_job(...)` still used a read-then-insert/update
pattern. Under concurrent callers, that could now race into an integrity error
instead of coalescing the replay intent cleanly.

## Decision

Make `RESET_WATERMARKS` creation one atomic database upsert.

## Change

- Replaced the read-then-update/create path with one SQL statement:
  - inserts a pending `RESET_WATERMARKS` job
  - or updates the existing pending job to the earliest impacted date
  - returns the surviving durable row
- Added unit coverage for the atomic upsert path.
- Added DB-backed integration coverage proving repeated `create_job(...)` calls
  leave one pending row with the earliest impacted date.

## Why This Is Better

- Removes a new concurrency seam introduced by the stronger DB uniqueness rule.
- Keeps replay-intent coalescing correct even under concurrent producer paths.
- Makes the durable queue invariant both schema-backed and race-safe.

## Evidence

- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`
