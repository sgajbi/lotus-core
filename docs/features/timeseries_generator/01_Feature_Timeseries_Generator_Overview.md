# Feature Documentation: Timeseries Generation and Portfolio Aggregation

## 1. Summary

The time-series layer is now split across two services:

- **`timeseries_generator_service`** owns position-level time-series generation from `daily_position_snapshots` into `position_timeseries`.
- **`portfolio_aggregation_service`** owns portfolio-level aggregation from `position_timeseries` into `portfolio_timeseries`.

Together, these time-series tables are the foundational datasets that power the entire `query_service`. All on-the-fly Performance (TWR) and Risk Analytics calculations are performed directly on this data. The split keeps position transformation and portfolio aggregation independently scalable while preserving the same read-model semantics.

## 2. Key Features

* **Two-Stage Aggregation:** The platform performs a two-stage process:
    1.  **Position Time-Series:** `timeseries_generator_service` transforms each individual `daily_position_snapshot` into a richer `position_timeseries` record, calculating daily cash flows and market values specific to that holding.
    2.  **Portfolio Time-Series:** `portfolio_aggregation_service` aggregates all of a portfolio's `position_timeseries` records for a given day into a single, consolidated `portfolio_timeseries` record, handling all necessary currency conversions.

* **Scheduled Aggregation:** The portfolio-level aggregation is not triggered directly by individual position events. Instead, it is managed by `portfolio_aggregation_service` through a background scheduler (`AggregationScheduler`) that creates jobs to ensure that a portfolio's daily record is only created after all its constituent position data is ready.

* **Epoch-Aware:** Both services are fully integrated with the reprocessing engine. All reads of snapshot data and all writes to the time-series tables are filtered and tagged with the correct `epoch`, ensuring consistency during historical data corrections.

## 3. Gaps and Design Considerations

* **Completeness Gating (Implemented):** Aggregation claim logic now enforces deterministic completeness for each portfolio/day/epoch before processing. A job is claimable only when `daily_position_snapshots` input count equals transformed `position_timeseries` count, in addition to sequential prior-day ordering rules.
