# RFC 018: Enhance Reprocessing Scalability and Resilience

* **Status**: Proposed
* **Date**: 2025-09-01

## 1. Summary

The current reprocessing engine is architecturally sound but has two potential weaknesses under heavy load or failure conditions: a "thundering herd" problem from back-dated prices on widely-held securities, and a state corruption risk if the `position-calculator` crashes mid-replay.

This RFC proposes introducing a dedicated, persistent job queue for price-based fan-outs to allow for rate-limiting, and making the transaction re-emission process in the `position-calculator` atomic to improve resilience.

## 2. Gaps and Proposed Solutions

### 2.1. Scalability: Price Update "Thundering Herd"

* **Gap:** A back-dated price for a security like an S&P 500 ETF could trigger simultaneous watermark resets for thousands of `position_state` keys. The current implementation fans this out in-memory, which could overwhelm the database and the `ValuationScheduler` with a sudden, massive burst of work.
* **Proposal:**
    1.  The `PriceEventConsumer` will no longer be responsible for finding affected portfolios.
    2.  Instead, the `ValuationScheduler` will read from the `instrument_reprocessing_state` table and, instead of fanning out in-memory, it will create discrete, persistent "ResetWatermarkJob" records in a new `reprocessing_jobs` table.
    3.  A separate worker process can then consume jobs from this table at a controlled rate, preventing the system from being overwhelmed.
    4.  **Add Metric:** A new Prometheus Gauge `instrument_reprocessing_triggers_pending` will be added to monitor the depth of the trigger queue.

### 2.2. Resilience: Non-Atomic Transaction Replay

* **Gap:** The `position-calculator` currently performs two separate actions in a non-atomic sequence: 1) it updates the `position_state` to increment the epoch, and 2) it begins publishing all historical transactions. If the service crashes after step 1 but before completing step 2, the key is left in a `REPROCESSING` state with no events in flight to complete the process, requiring manual intervention.
* **Proposal:**
    1.  Refactor the `position-calculator`'s trigger logic. Instead of publishing directly to Kafka, it will write all the historical transactions that need to be re-emitted into the `outbox_events` table within the **same database transaction** where it increments the `position_state` epoch.
    2.  The standard `OutboxDispatcher` will then reliably publish these events to Kafka. This makes the entire reprocessing trigger an atomic operation, guaranteeing that a key will not be marked for reprocessing unless the events required to complete it are durably queued for delivery.