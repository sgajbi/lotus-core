
# RFC 003 : Robust, Resilient & Scalable Valuation Pipeline 

## 1. Summary

The current valuation pipeline is not resilient to data timing issues. The scheduler creates valuation jobs for dates before a position actually exists, leading to `DataNotFoundError` exceptions in the consumer. These errors are incorrectly treated as retryable, which pollutes the Dead-Letter Queue (DLQ), causes consumer instability, and creates significant operational noise.

This proposal outlines a plan to make the pipeline robust by introducing **position-aware job scheduling**, a **durable job lifecycle**, and **smarter consumer error handling**.

---

## 2. Architectural Assessment & Refinements

This approach is a significant architectural improvement that simplifies the system while making it more robust.

* **Simplicity & Determinism**: The `position_state` table makes the state of each `(portfolio_id, security_id)` key **explicit and centralized**, moving away from a complex, implicit state spread across event streams. This makes the system's behavior deterministic and easier to reason about.
* **Resilience & Concurrency**: **Epoch fencing** is the core mechanism for safety, elegantly solving potential race conditions between a live data flow and a back-dated replay.
* **Scalability**: By scoping all reprocessing to an individual key, this design avoids disruptive, system-wide recalculations.
* **Observability**: The explicit state in the `position_state` table makes it trivial to monitor keys that are stuck in a `REPROCESSING` state or have a lagging `watermark_date`.

### 2.1. Refinements for Edge Cases

The following refinements will be incorporated into the implementation to handle specific edge cases:

1.  **Watermark Advancement Authority**:
    * **Refinement**: The **`ValuationScheduler` will be the sole authority** responsible for advancing the `watermark_date`. It will only do so after confirming that all valuation jobs for a contiguous date range have successfully completed.
2.  **"Thundering Herd" on Price Updates**:
    * **Refinement**: The `ValuationScheduler` must handle a sudden influx of reprocessing triggers gracefully. Its logic will batch queries on the `position_state` table and stagger the enqueuing of new valuation jobs to avoid overwhelming Kafka or downstream services.
3.  **API Read Experience During Reprocessing**:
    * **Refinement**: The API response for a key in a `REPROCESSING` state will be enhanced to include a status flag (e.g., `{"reprocessing_status": "IN_PROGRESS"}`) to inform the user that the data is being updated.
4.  **Rapid Back-to-Back Reprocessing**:
    * **Refinement**: The design handles this via chained epoch increments (e.g., `N` -> `N+1` -> `N+2`). The atomic `UPDATE` on the `position_state` table and epoch fencing in consumers are critical. This will be a priority for integration testing.

---

## 3. Proposed Changes

### 3.1. Database Schema Enhancement

We will introduce a durable lifecycle for valuation jobs by adding columns to the `portfolio_valuation_jobs` table.

* **New Columns**:
    * `attempt_count` (INTEGER)
    * `failure_reason` (TEXT)
* **New Statuses**:
    * The `status` field will be leveraged to include new terminal states like `SKIPPED_NO_POSITION`.

### 3.2. Position-Aware Job Scheduling

The `ValuationScheduler` will be modified to prevent creating jobs for dates where no position exists.

* **Fetch First Open Date**: The scheduler will determine the `first_open_date` for each `(portfolio, security, epoch)` key.
* **Adjust Backfill Start**: The job creation loop will start from `max(watermark_date + 1, first_open_date)`.

### 3.3. Intelligent Consumer Error Handling

The `ValuationConsumer` will be updated to distinguish between transient and permanent errors.

* **Retryable Errors**: Transient issues (e.g., DB connection errors) will remain retryable.
* **Permanent Errors (`DataNotFoundError`)**: When no position history is found, the consumer will mark the job `SKIPPED_NO_POSITION` and will **not** send the message to the DLQ.

---

## 4. High-Level Implementation Plan

1.  **DB Migration**: Add the `attempt_count` and `failure_reason` columns.
2.  **Consumer Logic**: Update the `ValuationConsumer` with the new error handling.
3.  **Repository Enhancement**: Add a method to find the `first_open_date` for securities.
4.  **Scheduler Logic**: Update the `ValuationScheduler` with position-aware logic.
5.  **Observability**: Add Prometheus metrics to monitor the new states.

 