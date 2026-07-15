# Portfolio Derived-State Materialization

## 1. Summary

The time-series layer is one supervised `portfolio_derived_state_service` deployable with two
separately testable capabilities:

- **Position time series** transforms `daily_position_snapshots` into `position_timeseries` and
  stages affected portfolio-day jobs.
- **Portfolio time series** claims durable `portfolio_aggregation_jobs` and aggregates
  `position_timeseries` into `portfolio_timeseries`.

Together, these tables are Core-owned inputs to query and downstream analytics products. The
modules retain independent concurrency and metrics while sharing one image, runtime supervisor,
health endpoint, and outbox dispatcher.

## 2. Key Features

* **Two-Stage Aggregation:** The platform performs a two-stage process:
    1. **Position Time-Series:** the position use case transforms each `daily_position_snapshot`
       into a `position_timeseries` record with holding-level daily cash flows and market values.
    2. **Portfolio Time-Series:** bounded aggregation workers combine a portfolio day's eligible
       position records into one `portfolio_timeseries` record with governed FX conversion.

* **Durable Scheduled Aggregation:** Position materialization idempotently stages database jobs.
  `AggregationScheduler` recovers and leases eligible work; no private Kafka command separates the
  modules.

* **Epoch-Aware:** Both capabilities filter and tag source reads and writes with the governed
  processing epoch for historical corrections.

## 3. Gaps and Design Considerations

* **Completeness Gating (Implemented):** Aggregation claim logic now enforces deterministic completeness for each portfolio/day/epoch before processing. A job is claimable only when `daily_position_snapshots` input count equals transformed `position_timeseries` count, in addition to sequential prior-day ordering rules.
