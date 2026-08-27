# Feature Documentation: Position Calculator

## 1. Summary

**Position processing** is the core backend capability, owned by the unified `portfolio_transaction_processing_service` runtime, that transforms the stream of individual, cost-calculated transactions into an auditable, chronological history of each security holding. Its primary output is the `position_history` table, which provides a running statement of quantity and cost basis after every transaction.

This service is also the system's primary defense against out-of-order data. It contains the logic to detect back-dated **transactions** and is responsible for initiating the entire **Epoch/Watermark Reprocessing** flow to ensure the portfolio's history is always accurate and deterministic.

## 2. Key Features

* **Position History Generation**: Consumes enriched transaction events and calculates the resulting position state (quantity and cost basis), creating a new record in `position_history` for each transaction. This provides a complete, auditable trail.
* **Back-dated Transaction Detection**: Contains the critical logic that identifies transactions arriving out of chronological order.
* **Atomic Reprocessing Trigger**: When a back-dated transaction is detected, this service is responsible for triggering a full replay of all historical transactions for that key. This entire trigger process—incrementing the `epoch` and queueing all historical events for re-emission—is performed as a single, atomic database transaction using the **Outbox Pattern**. This guarantees that a position will never be left in a corrupted or unrecoverable `REPROCESSING` state, even if the service crashes.