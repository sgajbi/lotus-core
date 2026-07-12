# CR-163: Stale Timeout Runtime Controls Review

## Summary

Replay, valuation, and aggregation queues already exposed retry ceilings, but the companion stale-processing timeout still lived as a hardcoded `15 minutes` default inside repository methods. That meant one of the most important recovery thresholds remained implicit at the data-access layer instead of being owned by the runtime that applies it.

## Findings

- `ValuationRepositoryBase.find_and_reset_stale_jobs(...)` accepted `timeout_minutes`, but `ValuationScheduler` always used the repository default.
- `ReprocessingJobRepository.find_and_reset_stale_jobs(...)` accepted `timeout_minutes`, but `ReprocessingWorker` always used the repository default.
- `TimeseriesRepositoryBase.find_and_reset_stale_jobs(...)` accepted `timeout_minutes`, but `AggregationScheduler` always used the repository default.

## Changes

- Added runtime settings for:
  - `VALUATION_SCHEDULER_STALE_TIMEOUT_MINUTES`
  - `REPROCESSING_WORKER_STALE_TIMEOUT_MINUTES`
  - `AGGREGATION_SCHEDULER_STALE_TIMEOUT_MINUTES`
- Wired the owning runtimes to pass those values explicitly to stale-reset repository calls.
- Added unit proof that the runtime settings objects and worker/scheduler instances carry the configured values.

## Result

The stale-processing timeout is now an explicit runtime-owned control alongside retry ceilings, not an implicit repository default hidden from operations and service owners.
