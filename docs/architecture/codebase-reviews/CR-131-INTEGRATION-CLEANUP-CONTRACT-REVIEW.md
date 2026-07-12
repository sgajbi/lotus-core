# CR-131 Integration Cleanup Contract Review

## Finding
`tests/conftest.py` truncated most durable state between tests but omitted `reprocessing_jobs`. Repository and integration tests that exercised the replay queue could therefore observe historical queue residue from earlier tests, even when the production repository behavior was correct.

## Change
Added `reprocessing_jobs` to `TABLES_TO_TRUNCATE` in [tests/conftest.py](C:/Users/Sandeep/projects/lotus-core/tests/conftest.py).

## Why This Is Correct
`reprocessing_jobs` is a durable control/work queue table. It belongs in the same cleanup contract as `portfolio_valuation_jobs`, `portfolio_aggregation_jobs`, `pipeline_stage_state`, and the other replay-control tables. Leaving it out makes integration outcomes depend on prior test history instead of the asserted invariant.

## Evidence
- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py -x -q`
- `python -m pytest tests/integration -x -q`
