# Reprocessing Triggers and Data Flows

Reprocessing can be initiated by two distinct types of back-dated events: transactions and market prices. Each follows a specific flow.

## 1. Transaction-Based Reprocessing Flow

This flow is triggered and managed by the **`position-calculator`** service.

1.  **Detection:** The service consumes a `transactions.cost.processed` event. It compares the `transaction_date` against an `effective_completed_date`. This effective date is the **later** of either the key's current `watermark_date` or the date of the latest `daily_position_snapshot` created for the current epoch. This use of the snapshot date provides a robust defense against stale watermarks.
2.  **State Update:** If the transaction is back-dated, the service atomically updates the `position_state` table for the `(portfolio_id, security_id)` key:
    * `epoch` is incremented (`N` -> `N+1`).
    * `status` is set to `REPROCESSING`.
    * `watermark_date` is reset to `transaction_date - 1 day`.
3.  **Event Replay:** The service queries the database for **all** historical transactions for that key. It then re-publishes them in chronological order to the `transactions.cost.processed` topic.
4.  **Epoch Propagation:** Crucially, each re-published event's payload now contains the new epoch number (e.g., `"epoch": N+1`). This allows downstream consumers to perform epoch fencing.

## 2. Price-Based Reprocessing Flow

This flow is more distributed and is designed to handle a price change that could affect many portfolios at once. It is managed by the **`position-valuation-calculator`**.

1.  **Detection (`PriceEventConsumer`):** A consumer listens for `market_prices.persisted` events. It compares the `price_date` to the system's latest `business_date`. If the price is for a past date, it's flagged.
2.  **Instrument-Level Trigger:** Instead of immediately finding every portfolio affected by this price (which could be thousands), the consumer creates a single, lightweight trigger record in the `instrument_reprocessing_state` table. This record flags the `security_id` and the `earliest_impacted_date`. If multiple back-dated prices for the same security arrive, the record is updated to reflect the earliest date, ensuring the reprocessing goes back far enough.
3.  **Scheduled Fan-Out (`ValuationScheduler`):** On its polling cycle, the `ValuationScheduler` checks the `instrument_reprocessing_state` table.
4.  **Watermark Reset:** When it finds a trigger, it performs a "fan-out" operation:
    * It queries to find all portfolios that hold the affected security.
    * For each of those portfolios, it updates the `position_state` table, resetting the `watermark_date` for that specific `(portfolio_id, security_id)` key to the date before the back-dated price.
5.  **Automatic Gap Filling:** Once the watermarks are reset, the scheduler's primary logic automatically detects these new gaps between the new watermarks and the current business date, creating the necessary valuation jobs to rebuild history under the existing epoch. This flow does **not** cause an epoch increment.