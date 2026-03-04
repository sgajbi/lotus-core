### **RFC 019: Standardize Epoch Fencing for Consumers**

  * **Status**: **Final**
  * **Date**: 2025-09-01
  * **Services Affected**: `portfolio-common`, `position_calculator`, `timeseries_generator_service`, `cashflow_calculator_service`
  * **Related RFCs**: [RFC 001 - Epoch and Watermark-Based Reprocessing](https://www.google.com/search?q=docs/RFCs/RFC%2520001%2520-%2520Epoch%2520and%2520Watermark-Based%2520Reprocessing.md)

-----

## 1\. Summary

Epoch fencing is the system's most critical pattern for guaranteeing data integrity during reprocessing flows. Its current implementation is manual, with boilerplate logic duplicated across multiple consumers (`PositionTimeseriesConsumer` , `PositionCalculator` consumer, etc.). This approach is error-prone, increases the cognitive load on developers, and violates the DRY (Don't Repeat Yourself) principle.

This RFC finalizes the proposal to abstract the epoch fencing logic into a reusable, robust, and observable utility class within the `portfolio-common` library. This will standardize the implementation, reduce code duplication, and simplify the development of all current and future "reprocessing-aware" consumers.

-----

## 2\. Architectural Assessment

This change represents a significant improvement in the maintainability and reliability of our event-driven architecture.

### **Pros**:

  * **Robustness & Correctness**: Centralizing the logic into a single, well-tested class eliminates the risk of subtle bugs or inconsistencies that can arise from manually re-implementing the check in multiple places.
  * **Reduced Boilerplate**: Consumers are simplified to a single check (`if not await fencer.check(event): return`), making them cleaner, easier to read, and faster to write.
  * **Simplified Development**: Developers creating new consumers no longer need to understand the low-level details of fetching `PositionState` or interacting with the repository. They only need to use the simple `EpochFencer` interface.
  * **Centralized Observability**: All logging and metric increments for stale, dropped messages are handled within the utility. This ensures that every fenced consumer reports these events in a consistent, standardized way using the existing `epoch_mismatch_dropped_total` metric.

### **Cons / Trade-offs**:

  * **Performance Consideration**: Each epoch check requires an asynchronous database call to the `position_state` table. This is an inherent and necessary cost of the epoch/watermark pattern. By centralizing this call, we create a single point for future optimization (e.g., adding a short-lived cache for `PositionState`) if it ever becomes a performance bottleneck.

-----

## 3\. High-Level Design

### 3.1. New `EpochFencer` Utility

A new class, `EpochFencer`, will be created in the `portfolio-common` library.

  * **Location**: `src/libs/portfolio-common/portfolio_common/reprocessing.py`
  * **Dependencies**: It will be initialized with an `AsyncSession` and will internally use the existing `PositionStateRepository`.
  * **Event Contract**: The `check` method will expect an event object that has `portfolio_id`, `security_id`, and `epoch` attributes. This contract will be enforced via a simple structural type check (`typing.Protocol`).
  * **Functionality**: The `check(event)` method will encapsulate the entire fencing process:
    1.  Extract the key (`portfolio_id`, `security_id`) and `epoch` from the event.
    2.  Call `PositionStateRepository.get_or_create_state` to get the current state for the key.
    3.  Compare the event's epoch to the state's epoch (`event.epoch < state.epoch`).
    4.  If the event is stale, it will automatically log a standardized warning and increment the `epoch_mismatch_dropped_total` metric.
    5.  It will return `False` if the message is stale and should be discarded, and `True` otherwise.

### 3.2. Example Usage

All relevant consumers will be refactored to use the new utility at the beginning of their message processing logic.

```python
// In a consumer's process_message method:
from portfolio_common.reprocessing import EpochFencer

# ...

async for db in get_async_db_session():
    async with db.begin():
        # ... setup repositories
        
        fencer = EpochFencer(db)
        if not await fencer.check(event):
            # The fencer handles all logging and metrics.
            # We just need to acknowledge and exit.
            return
        
        # ... proceed with business logic ...
```

-----

## 4\. Implementation Plan

1.  **Phase 1: Implement `EpochFencer` in `portfolio-common`**

      * Create the new file `src/libs/portfolio-common/portfolio_common/reprocessing.py`.
      * Define a `FencedEvent` protocol that requires `portfolio_id`, `security_id`, and `epoch` attributes.
      * Implement the `EpochFencer` class with its `check(event: FencedEvent)` method.
      * Add comprehensive unit tests in `tests/unit/libs/portfolio-common/` covering success, stale event, and new key scenarios. Ensure 100% test coverage for the new class.

2.  **Phase 2: Refactor Existing Consumers**

      * Identify all consumers that currently perform manual epoch fencing.
          * `PositionTimeseriesConsumer` in `timeseries_generator_service` 
          * `TransactionEventConsumer` in `position_calculator` 
          * `CashflowCalculatorConsumer` in `cashflow_calculator_service` (which currently passes epoch through but should have an explicit fence )
      * Modify each consumer listed above to instantiate and use the `EpochFencer`.
      * Remove the old, duplicated fencing logic from each consumer.
      * Update the unit tests for each refactored consumer to ensure the `EpochFencer` is called and that the consumer correctly exits when the fencer returns `False`.

3.  **Phase 3: Validation & Documentation**

      * Run the full E2E test suite, paying special attention to `test_reprocessing_workflow.py` and `test_rapid_reprocessing.py`, to provide end-to-end validation that the new, standardized implementation works correctly.
      * Create a new developer guide in the documentation.

-----

## 5\. Acceptance Criteria

  * The `EpochFencer` class is implemented in `portfolio-common` as described and has 100% unit test coverage.
  * The `PositionTimeseriesConsumer`, `TransactionEventConsumer` (in `position_calculator`), and `CashflowCalculatorConsumer` are all refactored to use the `EpochFencer`.
  * All manual epoch fencing logic is removed from the refactored consumers.
  * The `epoch_mismatch_dropped_total` metric is correctly incremented by the `EpochFencer` when a stale message is detected.
  * All existing E2E tests, particularly those covering reprocessing, pass without regressions.
  * A new developer guide, `docs/features/reprocessing_engine/05_Developer_Guide.md`, is created, explaining the epoch/watermark model and demonstrating the correct usage of the `EpochFencer` utility for building new consumers.

 