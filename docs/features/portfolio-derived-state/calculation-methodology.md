# Methodology Guide: Timeseries Generation and Portfolio Aggregation

This guide details the separate calculation policies used by the unified derived-state runtime to
create `position_timeseries` and `portfolio_timeseries`.

## 1. Position Time-Series Calculation

For each authoritative `daily_position_snapshot` event, the position-timeseries use case creates a
corresponding record for that business date and epoch.

* **Beginning-of-Day (BOD) Market Value:** This is sourced directly from the **End-of-Day (EOD)** `market_value_local` of the *previous day's* snapshot. If no previous day snapshot exists, it is set to zero.
* **End-of-Day (EOD) Market Value:** This is sourced directly from the `market_value_local` of the *current day's* snapshot.
* **Cash Flows:** The service queries the `cashflows` table for all flows associated with that specific security on that specific day. It then aggregates these flows based on their timing (`BOD` or `EOD`) and their type (`is_position_flow`, `is_portfolio_flow`) to populate the four distinct cash flow fields in the time-series record.
* **Fees:** Fees are derived from persisted `EXPENSE` cash flows and are emitted through analytics-input contracts as canonical `cash_flow_type="fee"` observations.

When a position snapshot is generated or restated, the consumer also recalculates dependent later
position-timeseries rows for the same portfolio/security while material state continues to change.
This keeps persisted BOD values aligned with prior persisted EOD state after replay, backfill, and
out-of-order snapshot publication.

The downstream query-control-plane analytics input contract applies an additional serving-time
continuity guard for TWR consumers. If a stored position-timeseries BOD value is stale relative to
the immediately preceding active EOD state, the analytics response uses the prior EOD value as
effective beginning capital. Positions that reappear after an absent date are not carried from stale
historical rows; if internal position-flow evidence explains the reappearance and there is no
portfolio-level external flow, they are treated as beginning capital rather than as
zero-to-market-value returns. Cash-book positions with only internal trade-settlement flows are
treated as capital-neutral for TWR input purposes so settlement cash swings do not create synthetic
portfolio returns. Portfolio-level external flows and operational fee flows remain explicit cash-flow
economics and are not converted into internal capital continuity repairs.

## 2. Portfolio Time-Series Aggregation

Portfolio time-series creation is a scheduled application capability in
`portfolio_derived_state_service` and runs only after position-level completeness is established.

* **Beginning-of-Day (BOD) Market Value:** This is aggregated from the effective beginning market values of the position-timeseries rows included in the analytics input contract. The serving path repairs stale position BOD values from prior EOD state before summing them for TWR consumers.
* **Cash Flows & Fees:** The aggregation service fetches all `position_timeseries` records for the portfolio on the given day and for the correct epoch. It iterates through them, performing the following steps:
    1.  It sums the `bod_cashflow_portfolio` and `eod_cashflow_portfolio` fields from each record.
    2.  If a position's currency is different from the portfolio's base currency, it fetches the appropriate FX rate for that day and converts the cash flow amount to the portfolio's base currency before adding it to the running total.
    3.  Fees are aggregated by summing the absolute value of any negative portfolio-level cash flows.
* **End-of-Day (EOD) Market Value:** The EOD market value is calculated by fetching all `daily_position_snapshots` for the portfolio on the given day that match the **target epoch**. It then sums the `market_value` (which is already in the portfolio's base currency) from these definitive snapshot records. This ensures the final value is correct and not subject to potential FX conversion errors during aggregation.
