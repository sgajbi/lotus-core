This is an excellent proposal. The diagnosis of the race condition between the `position-calculator` and the `ValuationScheduler` is accurate, and the reliance on `daily_position_snapshots` as a more reliable source of truth for "work completed" is the correct architectural path. This change moves the system from a timing-dependent, fragile state to a deterministic one.

The proposal is approved. Please produce the final RFC, ensuring it is ready for implementation. Include the required documentation updates in the acceptance criteria.

-----

### **RFC 004: Make Reprocessing Deterministic**

  * **Status**: **Final** (was: Draft)
  * **Date**: 2025-09-02
  * **Lead**: Gemini Architect
  * **Services Affected**: `position-calculator`, `position-valuation-calculator`
  * **Related RFCs**: [RFC 001 - Epoch and Watermark-Based Reprocessing](https://www.google.com/search?q=docs/RFCs/RFC%2520001%2520-%2520Epoch%2520and%2520Watermark-Based%2520Reprocessing.md)

-----

## 1\. Summary

The system's back-dated transaction detection mechanism is currently non-deterministic due to a race condition. The `position-calculator` relies exclusively on `position_state.watermark_date` to detect back-dated events. However, this watermark is advanced by the `ValuationScheduler` in a separate process. If a back-dated transaction is consumed before the scheduler has advanced the watermark, it is incorrectly processed as a current event, which prevents the reprocessing `epoch` from being incremented and leads to critical data integrity failures.

This RFC finalizes a three-part solution to make this process deterministic and resilient:

1.  **Harden the back-dated event detector** in the `position-calculator` to use the latest `DailyPositionSnapshot` date as the primary source of truth, making the detection independent of the scheduler's timing.
2.  **Improve the `ValuationScheduler`'s reliability** to ensure it consistently advances watermarks and provides clear operational logging.
3.  **Formalize epoch propagation** in all relevant Kafka events to guarantee strict data fencing during a replay.

-----

## 2\. Decision

We will refactor the back-dated transaction detection logic in the `position-calculator` service. It will now determine an `effective_completed_date` by taking the **later** of either the key's `watermark_date` or the date of its latest `daily_position_snapshot` for the current epoch. This removes the race condition and ensures reprocessing is always triggered correctly.

Additionally, we will enforce that the new `epoch` is propagated in the payloads of all re-emitted transaction events, and all downstream consumers will be updated to use the standardized `EpochFencer` utility to prevent data corruption from stale messages.

-----

## 3\. Architectural Consequences

### Pros

  * **Correctness & Determinism**: This change eliminates the race condition entirely. A back-dated event will now **always** be detected correctly, regardless of the operational state or timing of the `ValuationScheduler`.
  * **Resilience**: By using the `daily_position_snapshot` as the ground truth for "work completed," the system becomes more resilient. The detection logic is now based on the actual persisted state of the pipeline's output.
  * **Maintainability**: Formalizing the use of the `EpochFencer` utility across all relevant consumers reduces code duplication and simplifies the development of future reprocessing-aware services.

### Cons / Trade-offs

  * **Increased I/O**: The detector will perform one additional indexed `SELECT` query per incoming transaction to check for the latest snapshot date. This is a minor and acceptable performance trade-off for the significant gain in data integrity and correctness.

-----

## 4\. High-Level Design

### 4.1. Hardened Back-Dated Detector (`position-calculator`)

The logic in `position_logic.py` will be modified.

  * **New Repository Method**: A new method will be added to `PositionRepository` (`src/services/calculators/position_calculator/app/repositories/position_repository.py`)
    ```python
    async def get_latest_completed_snapshot_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
    ```
  * **Updated Detection Logic**: The `PositionCalculator.calculate` method will be updated to :
    1.  Fetch the `current_state` (including `watermark_date` and `epoch`) for the event's key.
    2.  Call the new repository method to get the `latest_snapshot_date` for the current epoch.
    3.  Determine the `effective_completed_date = max(current_state.watermark_date, latest_snapshot_date)`.
    4.  A transaction is back-dated if `transaction_date < effective_completed_date`.

### 4.2. Epoch Propagation & Fencing

  * **`position-calculator`**: When a reprocessing flow is triggered, the service will re-emit all historical `processed_transactions_completed` events. Each re-emitted `TransactionEvent` payload **must** now include the new `epoch` number: 2907, 3456].
  * **All Consumers**: All consumers of `processed_transactions_completed` and other epoch-versioned events (`cashflow_calculator_service`, `timeseries_generator_service`, `position_calculator`) must use the standardized `EpochFencer` utility at the beginning of their processing logic to discard stale messages.

-----

## 5\. Database Changes

No schema changes are required. However, the existing index on `daily_position_snapshots` should be reviewed to ensure it efficiently covers the new `MAX(date)` query.

  * **Verify Index**: The existing `ix_daily_position_snapshots_covering` index on `(portfolio_id, security_id, date DESC, id DESC)` is already well-suited for this query. No changes are needed.

-----

## 6\. Testing Plan

  * **Unit Tests**:
      * Add a new unit test for the `PositionRepository.get_latest_completed_snapshot_date` method.
      * Add unit tests for the `PositionCalculator.calculate` logic to verify that `is_backdated` is correctly evaluated using both the watermark and the snapshot date.
  * **Integration Tests**:
      * Add an integration test for `TransactionEventConsumer` verifying that a back-dated event (mocked to have a later snapshot date) correctly triggers the reprocessing flow (`increment_epoch_and_reset_watermark` and `create_outbox_event` are called).
  * **End-to-End (E2E) Tests**:
      * The primary validation will be fixing the existing, failing E2E tests: `test_reprocessing_workflow.py` and `test_rapid_reprocessing.py`. Their successful execution will prove the entire flow is deterministic and correct.

-----

## 7\. Documentation Updates

To ensure documentation remains current, the following updates are required:

  * **`docs/features/reprocessing_engine/02_Triggers_and_Flows.md`**:
      * Update the "Detection" step under "Transaction-Based Reprocessing Flow" to describe the new logic of using the **later** of the `watermark_date` or the latest `daily_position_snapshot` date as the `effective_completed_date`:.
  * **`docs/features/position_calculator/03_Methodology_Guide.md`**:
      * Update the "Back-dated Transaction Detection" section to reflect the new, more robust `effective_completed_date` logic, explaining why it's more reliable than using the watermark alone.

-----

## 8\. Acceptance Criteria

1.  The `PositionRepository` in `position-calculator` is updated with the `get_latest_completed_snapshot_date` method.
2.  The `PositionCalculator` logic is refactored to use the `effective_completed_date` for back-dated detection.
3.  When reprocessing is triggered, the `position-calculator` re-emits `TransactionEvent` payloads that include the new, incremented `epoch`.
4.  All required consumers of epoch-versioned events correctly implement the shared `EpochFencer` utility.
5.  All new logic is covered by unit and integration tests.
6.  The E2E tests `test_reprocessing_workflow.py` and `test_rapid_reprocessing.py` **must pass**.
7.  The documentation in `docs/features/reprocessing_engine/` and `docs/features/position_calculator/` is updated to reflect the new detection methodology.