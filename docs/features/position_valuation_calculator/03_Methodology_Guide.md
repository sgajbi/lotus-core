# Methodology Guide: Position Valuation & Scheduling

This guide details the methodologies used by the `position-valuation-calculator` for both its calculation and orchestration responsibilities.

## 1. Valuation Logic

The core calculation is performed by the stateless `ValuationLogic` class. It determines a position's market value and unrealized profit & loss (P&L) in both the instrument's local currency and the portfolio's base currency.

### Calculation Steps

1.  **Align Price Currency:** If the provided market price's currency is different from the instrument's currency, an FX rate is used to convert the price into the instrument's currency.
2.  **Calculate Local Values:**
    * `Market Value (Local) = Quantity * Price (in instrument's currency)`
    * `Unrealized P&L (Local) = Market Value (Local) - Cost Basis (Local)`
3.  **Convert to Base Currency:**
    * If the instrument's currency is different from the portfolio's base currency, the `instrument_to_portfolio_fx_rate` is applied to the local currency values.
    * `Market Value (Base) = Market Value (Local) * FX Rate`
4.  **Calculate Base P&L:**
    * `Unrealized P&L (Base) = Market Value (Base) - Cost Basis (Base)`

### Current Behavior for Missing Data

* If a required FX rate for a valuation is not found in the database, the valuation cannot be completed. The resulting `daily_position_snapshot` is marked with a status of `FAILED`, and the corresponding valuation job is marked `COMPLETE`. The system **does not** automatically retry this job; a manual reprocessing trigger is required if the missing data is later ingested.

## 2. Valuation Scheduler Logic

The `ValuationScheduler` is a powerful background process that orchestrates all valuation and backfill activities. It runs in a continuous loop, performing a series of state management and job creation tasks.

### Scheduler's Main Loop

1.  **Process Instrument Triggers:** The scheduler first checks the `instrument_reprocessing_state` table. If it finds triggers from back-dated price events, it fans out by finding all affected portfolios and resetting their watermarks in the `position_state` table.
2.  **Reset Stale Jobs:** It runs a recovery query to find any jobs that have been in a `PROCESSING` state for too long (default > 15 minutes). These jobs are reset to `PENDING`, allowing them to be picked up again by a consumer. This makes the system resilient to worker crashes.
3.  **Create Backfill Jobs:** The scheduler queries the `position_state` table for all keys where the `watermark_date` is older than the latest system `business_date`. For each of these "lagging" keys, it creates the necessary `valuation.job.requested` jobs to fill the gap.
    * **Position-Aware Scheduling:** This process is intelligent; it will not create a job for a date that is before the position's first known transaction date, preventing unnecessary work.
4.  **Advance Watermarks:** After creating new jobs, the scheduler checks which lagging keys now have a complete, contiguous history of `daily_position_snapshots`. For these keys, it advances their `watermark_date` in the `position_state` table to the last contiguous date. If the new watermark matches the latest business date, the key's `status` is set back to `CURRENT`.
5.  **Dispatch Jobs:** Finally, the scheduler queries for all `PENDING` jobs in the `portfolio_valuation_jobs` table, atomically claims a batch of them by setting their status to `PROCESSING`, and publishes them as events to the `valuation.job.requested` Kafka topic.