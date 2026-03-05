# Feature Documentation: Timeseries Generator

## 1. Summary

The **`timeseries_generator_service`** is the final and most critical service in the data processing pipeline. Its sole purpose is to consume the daily valued positions (`daily_position_snapshots`) and aggregate them into the final, query-optimized time-series tables (`position_timeseries` and `portfolio_timeseries`).

These time-series tables are the foundational datasets that power the entire `query_service`. All on-the-fly Performance (TWR) and Risk Analytics calculations are performed directly on this data. The pre-aggregation performed by this service is the key to providing high-performance analytics on the read side.

## 2. Key Features

* **Two-Stage Aggregation:** The service performs a two-stage process:
    1.  **Position Time-Series:** First, it transforms each individual `daily_position_snapshot` into a richer `position_timeseries` record, calculating daily cash flows and market values specific to that holding.
    2.  **Portfolio Time-Series:** Second, it aggregates all of a portfolio's `position_timeseries` records for a given day into a single, consolidated `portfolio_timeseries` record, handling all necessary currency conversions.

* **Scheduled Aggregation:** The portfolio-level aggregation is not triggered directly by individual position events. Instead, it is managed by a background scheduler (`AggregationScheduler`) that creates jobs to ensure that a portfolio's daily record is only created after all its constituent position data is ready.

* **Epoch-Aware:** The service is fully integrated with the reprocessing engine. All reads of snapshot data and all writes to the time-series tables are filtered and tagged with the correct `epoch`, ensuring consistency during historical data corrections.

## 3. Gaps and Design Considerations

* **Completeness Gating (Implemented):** Aggregation claim logic now enforces deterministic completeness for each portfolio/day/epoch before processing. A job is claimable only when `daily_position_snapshots` input count equals transformed `position_timeseries` count, in addition to sequential prior-day ordering rules.
