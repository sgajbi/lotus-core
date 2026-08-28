# Feature Documentation: Position Processing

## 1. Summary

**Position processing** is the core backend capability, owned by the unified `portfolio_transaction_processing_service` runtime, that maintains an auditable, chronological history of each security holding. It does not consume a stream of already cost-calculated events: `TransactionProcessingConsumer` receives `transactions.persisted`, and cost, cashflow, and position effects are applied together in one atomic use case. Its primary output is the `position_history` table, which provides a running statement of quantity and cost basis after every transaction.

The same runtime is the system's primary defense against out-of-order data. It detects back-dated **transactions** and drives the **Epoch/Watermark Reprocessing** flow so the portfolio's history stays accurate and deterministic.

## 2. Key Features

* **Position History Generation**: Calculates the resulting position state (quantity and cost basis) for each persisted transaction, creating a `position_history` record. This provides a complete, auditable trail.
* **Back-dated Transaction Detection**: Contains the critical logic that identifies transactions arriving out of chronological order.
* **Atomic Backdated Rebuild**: When a back-dated transaction is detected, `PositionHistoryProcessor` (`app/application/position_history.py`) rebuilds the affected position stream **inline in the new epoch**, under the unit of work's row lock, using the plan from `plan_backdated_recalculation`. Historical events are not re-emitted onto a topic for a second pass. Because the rebuild and the epoch advance commit in the same transaction, a position cannot be left in a corrupted or unrecoverable `REPROCESSING` state if the process crashes. Events carrying an epoch older than the current one are discarded as stale.