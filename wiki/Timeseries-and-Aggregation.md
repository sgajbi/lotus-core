# Timeseries and Aggregation

## Purpose

This page explains the current time-series materialization path in `lotus-core`.

It is grounded in the active runtime split between:

- `timeseries_generator_service`
  position-timeseries materialization and aggregation-job staging
- `portfolio_aggregation_service`
  portfolio-level aggregation dispatch, computation, and completion publication

## What the runtime handles

The current implementation centers on:

- consuming persisted valuation snapshot events
- materializing or rematerializing `position_timeseries`
- re-arming `portfolio_aggregation_jobs` when material state changes
- dispatching eligible aggregation jobs onto the portfolio aggregation worker topic
- computing and upserting `portfolio_timeseries`
- publishing `portfolio_day.aggregation.completed` for downstream control workflows

This is a two-service materialization path, not one monolithic time-series worker.

## Service split

### `timeseries_generator_service`

This service consumes `valuation.snapshot.persisted` and is responsible for:

- computing `position_timeseries`
- detecting whether a new record is materially different from the existing one
- staging `portfolio_aggregation_jobs` when the portfolio-day aggregate must be recalculated
- propagating dependent recomputation forward when later rows for the same key are affected

The current consumer logic stages aggregation jobs directly in the database rather than emitting a
separate Kafka completion topic for position-timeseries generation.

### `portfolio_aggregation_service`

This service is responsible for:

- claiming eligible `portfolio_aggregation_jobs`
- dispatching portfolio-day aggregation work onto `portfolio_day.aggregation.job.requested`
- consuming those job requests
- computing `portfolio_timeseries` from the relevant `position_timeseries` set
- emitting `portfolio_day.aggregation.completed` after portfolio-level materialization succeeds

This keeps portfolio-level rollup execution separate from position-timeseries rematerialization.

## Runtime flow

The active path is:

1. valuation computes and persists a `daily_position_snapshot`
2. `position_valuation_calculator` emits `valuation.snapshot.persisted`
3. `timeseries_generator_service` consumes that event
4. `timeseries_generator_service` computes or updates `position_timeseries`
5. if material state changed, it stages `portfolio_aggregation_jobs`
6. `portfolio_aggregation_service` scheduler claims eligible jobs and publishes
   `portfolio_day.aggregation.job.requested`
7. `portfolio_aggregation_service` worker consumes the job request and upserts
   `portfolio_timeseries`
8. `portfolio_aggregation_service` emits `portfolio_day.aggregation.completed`
9. `pipeline_orchestrator_service` uses that completion signal to trigger downstream
   reconciliation controls

This sequence matches the current trigger matrix and runtime code. It does not assume the planned
RFC-081 future topology where more stage transitions are orchestrator-issued.

## Why it matters

If this path is stale or incorrect:

- analytics-input products for portfolio and position timeseries become incomplete
- support surfaces can show valuation completion without matching time-series readiness
- reconciliation can fail because portfolio-level aggregates no longer match the underlying
  position-timeseries rows
- downstream performance and risk services can consume lagging or partial source inputs

That is why timeseries and aggregation are part of the core derived-state contract, not just an
internal convenience layer.

## Boundary rules

- valuation snapshot persistence is upstream input
- `timeseries_generator_service` owns position-timeseries materialization and aggregation-job staging
- `portfolio_aggregation_service` owns portfolio aggregation dispatch and portfolio-timeseries
  computation
- downstream analytics services consume these outputs but do not redefine them

## Operational hints

Check this path when:

- `daily_position_snapshots` are current but portfolio or position timeseries are stale
- support evidence shows aggregation jobs not being re-armed or drained
- timeseries integrity reconciliation reports missing or mismatched `portfolio_timeseries`
- portfolio-level readiness lags behind security-level valuation completion

Check beyond this path when:

- valuation itself is incomplete
- support or replay evidence points to ingestion, replay, or earlier calculator drift
- downstream analytics interpretation is wrong while core timeseries inputs are already correct

## Related references

- [Timeseries Generator Service](Timeseries-Generator-Service)
- [Support and Lineage](Support-and-Lineage)
- [Financial Reconciliation](Financial-Reconciliation)
- [System Data Flow](System-Data-Flow)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
