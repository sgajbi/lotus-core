# Methodology Guide: Timeseries Generation and Portfolio Aggregation

This guide details the methodologies used by the split time-series layer to create its two primary data outputs: the `position_timeseries` and `portfolio_timeseries` tables.

## 1. Position Time-Series Calculation

For each `daily_position_snapshot` event it receives, `timeseries_generator_service` creates a corresponding `position_timeseries` record for that specific day and epoch.

* **Beginning-of-Day (BOD) Market Value:** This is sourced directly from the **End-of-Day (EOD)** `market_value_local` of the *previous day's* snapshot. If no previous day snapshot exists, it is set to zero.
* **End-of-Day (EOD) Market Value:** This is sourced directly from the `market_value_local` of the *current day's* snapshot.
* **Cash Flows:** The service queries the `cashflows` table for all flows associated with that specific security on that specific day. It then aggregates these flows based on their timing (`BOD` or `EOD`) and their type (`is_position_flow`, `is_portfolio_flow`) to populate the four distinct cash flow fields in the time-series record.
* **Fees:** Fees are derived from cash flows that are classified as expenses.

## 2. Portfolio Time-Series Aggregation

The creation of the portfolio-level time-series is a scheduled aggregation process owned by `portfolio_aggregation_service` and runs after the position-level data for a given day has been generated.

* **Beginning-of-Day (BOD) Market Value:** This is sourced directly from the **End-of-Day (EOD)** `eod_market_value` of the *previous day's* `portfolio_timeseries` record.
* **Cash Flows & Fees:** The aggregation service fetches all `position_timeseries` records for the portfolio on the given day and for the correct epoch. It iterates through them, performing the following steps:
    1.  It sums the `bod_cashflow_portfolio` and `eod_cashflow_portfolio` fields from each record.
    2.  If a position's currency is different from the portfolio's base currency, it fetches the appropriate FX rate for that day and converts the cash flow amount to the portfolio's base currency before adding it to the running total.
    3.  Fees are aggregated by summing the absolute value of any negative portfolio-level cash flows.
* **End-of-Day (EOD) Market Value:** The EOD market value is calculated by fetching all `daily_position_snapshots` for the portfolio on the given day that match the **target epoch**. It then sums the `market_value` (which is already in the portfolio's base currency) from these definitive snapshot records. This ensures the final value is correct and not subject to potential FX conversion errors during aggregation.
