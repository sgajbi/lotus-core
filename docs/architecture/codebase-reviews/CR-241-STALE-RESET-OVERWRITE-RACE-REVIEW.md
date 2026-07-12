# CR-241 Stale Reset Overwrite Race Review

## Scope

- Replay stale-reset repository path
- Valuation stale-reset repository path
- Aggregation stale-reset repository path

## Finding

All three stale-reset implementations used a two-step pattern:

1. select stale `PROCESSING` rows
2. update the selected ids to `PENDING` or `FAILED`

That second step did not re-check that the row was still:

- `status = 'PROCESSING'`
- older than the stale cutoff

This left a real race-condition gap. A worker could complete or re-claim a row after the stale
scan but before the stale reset update, and the stale reset sweep could overwrite live state back
to `PENDING` or `FAILED`.

## Action Taken

- Added update-time guards to all three stale-reset paths:
  - `status == 'PROCESSING'`
  - `updated_at < stale_cutoff`
- Added unit coverage proving the guarded update statements
- Added DB-backed integration characterization tests proving a concurrent completion is not
overwritten by the stale reset sweep

## Why This Matters

This is banking-grade control-path correctness work, not cosmetic cleanup. Stale recovery loops
must never resurrect already-completed durable work or downgrade a live owner under contention.

## Evidence

- Code:
  - `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
  - `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
  - `src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py`
- Unit tests:
  - `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
  - Result: `29 passed`
- DB-backed proof:
  - `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py -k overwrite_completed_rows -q`
  - `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py -k overwrite_completed_rows -q`
  - `python -m pytest tests/integration/services/timeseries_generator_service/test_int_timeseries_repo.py -k overwrite_completed_rows -q`
  - Result: each passed
- Quality gate:
  - `python scripts/openapi_quality_gate.py`
  - touched-surface `ruff check`

## Follow-up

- Keep applying the same review pattern anywhere stale reset or retry recovery uses:
  - select stale rows first
  - then update by id later
- If future worker families add stale recovery, require update-time ownership re-checks from the
  first implementation rather than fixing it after heavy-gate discovery.
