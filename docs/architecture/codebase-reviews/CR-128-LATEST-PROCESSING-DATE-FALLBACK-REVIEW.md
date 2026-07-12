# CR-128 Latest Processing Date Fallback Review

## Finding

`ValuationScheduler._advance_watermarks()` and `_create_backfill_jobs()` both depend on
`ValuationRepository.get_latest_business_date()`.

That contract assumed `business_dates` is always populated. In practice, some valid
workflows still generate valuation jobs and daily snapshots without seeding the
calendar table first. In those cases:

- valuation jobs could complete
- snapshots and position timeseries could exist
- but `latest_business_date` resolved to `None`
- so watermark advancement and terminal `REPROCESSING -> CURRENT` normalization
  became a no-op

This leaked live replay state across E2E modules even though the data plane was done.

## Change

`ValuationRepository.get_latest_business_date()` now falls back to the latest date
observed in actual valuation processing state when the business calendar is empty:

- `max(business_dates.date)`
- else `max(daily_position_snapshots.date, portfolio_valuation_jobs.valuation_date)`

## Why It Matters

This is a control-plane correctness fix.

The scheduler should use the canonical business calendar when it exists, but it must
still be able to normalize durable replay state based on real completed work when the
calendar table has not been seeded.

Without this fallback:

- the data plane can be complete
- the control row can stay stuck in `REPROCESSING`
- downstream aggregation and E2E cleanup will continue to see live work forever

## Evidence

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`
- `tests/e2e/test_5_day_workflow.py`
- `tests/e2e/test_avco_workflow.py`
- `tests/e2e/test_cashflow_pipeline.py`
