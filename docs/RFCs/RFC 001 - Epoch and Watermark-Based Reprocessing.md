# RFC: Epoch and Watermark-Based Reprocessing

This document outlines a new architecture for handling back-dated events in the lotus-core platform. It replaces the complex, implicit recalculation logic with a deterministic, epoch-based reprocessing model.

### **1. Summary**

The current recalculation system is complex and prone to race conditions. We will replace it with a simplified model using a per-key **epoch** and **watermark**.

- A **key** is the combination of `(portfolio_id, security_id)`.
- The **epoch** is an integer version number for the history of a key. All current data for a key shares the same epoch.
- The **watermark** is a date that indicates how far the system has successfully calculated for a key's current epoch.

When a back-dated event occurs, the system will increment the epoch for the affected key, reset its watermark, and deterministically rebuild its history under the new epoch. The `ValuationScheduler` will be the sole authority for creating valuation jobs, filling any gaps between a key's watermark and the current business date.

### **2. Architectural Assessment**

#### **Key Architectural Improvements**

-   **Simplicity & Determinism**: The current system relies on a complex choreography of events where the overall state is implicit. The new epoch/watermark model makes the state of each `(portfolio_id, security_id)` key **explicit and centralized** in the `position_state` table. This makes the system's behavior deterministic and easier to reason about.
-   **Resilience & Concurrency**: **Epoch fencing** is the core mechanism for safety. It elegantly solves potential race conditions between a live data flow and a back-dated replay. Any consumer processing a message with an `epoch` that does not match the *current* `epoch` in the `position_state` table will simply discard the message, preventing data corruption.
-   **Scalability**: By scoping all reprocessing to an individual key, the design avoids system-wide recalculations. A back-dated event for a single stock only impacts the portfolios holding it, which is a massive performance and scalability win.
-   **Observability**: The explicit state in the `position_state` table makes it trivial to monitor. We can now create alerts for keys that have been in a `REPROCESSING` state for too long or have a `watermark_date` that is lagging significantly.

#### **Edge Cases & Refinements**

1.  **Watermark Advancement Authority**
    -   **Edge Case**: If multiple services (e.g., the scheduler and the valuation worker) can update the watermark, it could lead to inconsistent state or partially completed backfills.
    -   **Refinement**: The **`ValuationScheduler` will be the sole authority** responsible for advancing the `watermark_date`. It will only do so after confirming that all valuation jobs for a contiguous date range `[current_watermark + 1, D]` have successfully completed.

2.  **"Thundering Herd" on Price Updates**
    -   **Edge Case**: A back-dated price update for a widely held security (e.g., an index ETF) could trigger watermark resets for thousands of keys simultaneously, potentially overwhelming the system.
    -   **Refinement**: The `ValuationScheduler` must handle this gracefully. Its logic for creating jobs will be designed to batch its queries on the `position_state` table and stagger the enqueuing of new valuation jobs to avoid overwhelming Kafka or downstream services.

3.  **API Read Experience During Reprocessing**
    -   **Edge Case**: During reprocessing, API queries will return the last known *good* data from the previous epoch, which is safe but could be confusing to a user.
    -   **Refinement**: The API response for a key in a `REPROCESSING` state will be enhanced to include a status flag (e.g., `{"reprocessing_status": "IN_PROGRESS"}`). This allows front-end applications to inform the user that the data is currently being updated.

4.  **Rapid Back-to-Back Reprocessing**
    -   **Edge Case**: Multiple back-dated events for the same key arrive in quick succession.
    -   **Refinement**: The design handles this via chained epoch increments (e.g., `N` -> `N+1` -> `N+2`). The atomic `UPDATE` on the `position_state` table and the epoch fencing in consumers are critical. This scenario will be a priority for integration testing.

### **3. Data Model Changes**

We will introduce one new table and add an `epoch` column to all versioned historical data.

1.  **New Table: `position_state`**
    -   **Purpose**: Tracks the current reprocessing state for each `(portfolio_id, security_id)` key.
    -   **Columns**:
        -   `portfolio_id` (VARCHAR, PK)
        -   `security_id` (VARCHAR, PK)
        -   `epoch` (INTEGER, NOT NULL, DEFAULT 0)
        -   `watermark_date` (DATE, NOT NULL)
        -   `status` (VARCHAR, NOT NULL, DEFAULT 'CURRENT') - e.g., CURRENT, REPROCESSING
        -   `updated_at` (TIMESTAMPZ)

2.  **Column Additions: `epoch`**
    -   An `epoch` (INTEGER, NOT NULL, DEFAULT 0) column will be added to the following tables to version their records:
        -   `position_history`
        -   `daily_position_snapshots`
        -   `position_timeseries`
        -   `portfolio_timeseries`
        -   `portfolio_valuation_jobs`
    -   Unique constraints on these tables will be updated to include the `epoch` column, for example: `UNIQUE(portfolio_id, security_id, date, epoch)` on `daily_position_snapshots`.

### **4. State Transitions & Logic Flow**

#### **A. Back-dated Transaction Flow**

1.  **Detection**: The `position-calculator` service consumes a `processed_transactions_completed` event and detects that its `transaction_date` is before the key's current `watermark_date`.
2.  **Epoch Increment**: It atomically updates the `position_state` for the key: `epoch++`, `watermark_date = transaction_date - 1 day`, `status = 'REPROCESSING'`. This acts as a lock.
3.  **Re-emit**: It fetches *all* historical transactions for the key and re-emits them in chronological order to the `processed_transactions_completed` topic. Each re-emitted event includes a `reprocess_epoch: <new_epoch>` header.
4.  **Reprocessing**: The pipeline consumes these events. All writes to `position_history` are tagged with the new epoch. Stale messages from the old epoch are ignored.

#### **B. Back-dated Price Flow**

1.  **Detection**: The `position-valuation-calculator`'s `price_event_consumer` detects a back-dated `market_price_persisted` event.
2.  **Trigger**: It identifies all affected `(portfolio_id, security_id)` keys and for each, atomically updates the `position_state`: `watermark_date = MIN(current_watermark, price_date - 1 day)`.
3.  **No Re-emission**: The `ValuationScheduler` will automatically detect the gap and schedule the necessary backfill.

#### **C. Valuation & Watermark Advancement (ValuationScheduler)**

The `ValuationScheduler` becomes the sole producer of valuation jobs. On its polling cycle:

1.  **Scan**: It queries `position_state` for all keys where `watermark_date < latest_business_date`.
2.  **Enqueue**: For each such key, it creates idempotent valuation jobs for the date range `[watermark_date + 1, latest_business_date]`, tagging each job with the key's **current epoch**.
3.  **Execute**: The `position-valuation-calculator` consumes these jobs, reads `position_history` for the job's epoch, and creates `daily_position_snapshots` tagged with the same epoch.
4.  **Advance Watermark**: After confirming a contiguous batch of snapshots up to date `D` has been successfully created, the scheduler updates the key's `watermark_date` to `D`.
5.  **Completion**: When `watermark_date == latest_business_date`, the scheduler updates the key's `status` to `CURRENT`.

### **5. Concurrency and Guarantees**

-   **Epoch Fencing**: The `epoch` number acts as a fencing token. Any consumer processing a message with an `epoch` that does not match the *current* `epoch` in the `position_state` table will discard the message.
-   **Idempotency**: All job creation and data writes are idempotent based on their natural keys plus the `epoch`, preventing duplicates from retries.
-   **Ordering**: Kafka partitioning by `portfolio_id` ensures that all events for a given portfolio are processed in order by a single consumer instance.

### **6. API / Reader Logic**

The `query-service` will be modified to only return data for the current, complete state. All queries for historical data will join with the `position_state` table and filter records where `table.epoch = position_state.epoch`. The API response may also be enhanced to include the `reprocessing_status`.

### **7. Observability**

-   **Metrics**: `reprocessing_active_keys_total`, `snapshot_lag_seconds`, `epoch_mismatch_dropped_total`, `scheduler_gap_days`.
-   **Logging**: All logs related to reprocessing will be structured with `portfolio_id`, `security_id`, `epoch`, and `watermark_date`.
-   **Tracing**: Spans will be tagged with the `epoch`.

### **8. Pros and Cons**

-   **Pros**: Deterministic, simple and explicit state, resilient to race conditions.
-   **Cons**: Higher write amplification during reprocessing, potential for brief data lag for the affected key on the API.

### **9. Acceptance Criteria**

-   The old `recalculation_jobs` table and `recalculation-service` are fully removed.
-   `position-calculator` no longer creates valuation or recalculation jobs directly.
-   Back-dated transactions and prices trigger the epoch/watermark flow correctly.
-   The `ValuationScheduler` is the only service that creates `portfolio_valuation_jobs`.
-   All E2E tests, including a new back-dated scenario, pass.
-   API queries only return data from the latest complete epoch.