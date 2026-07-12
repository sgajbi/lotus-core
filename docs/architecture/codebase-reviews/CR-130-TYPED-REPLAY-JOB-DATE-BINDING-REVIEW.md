# CR-130 Typed Replay-Job Date Binding Review

## Finding

CR-126 moved pending `RESET_WATERMARKS` creation onto one atomic SQL upsert, but the
real asyncpg path still treated the impacted date parameter as ambiguous.

That exposed a real gap between unit-level intent and database-level execution:

- repository logic was correct in shape
- but the date parameter was passed as an untyped string
- asyncpg could not infer the parameter type inside the `CAST(:earliest_impacted_date AS date)` path

## Change

Bound the replay-job parameters explicitly:

- `security_id` as `String`
- `earliest_impacted_date` as `Date`

and passed the impacted date as a parsed `date` instance on execution.

## Why It Matters

Replay queue hardening is only real if the atomic path works on the actual database
driver. A repository-level contract that passes unit tests but fails under asyncpg is
not a completed hardening slice.

## Evidence

- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`
