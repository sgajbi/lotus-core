## RFC 005: Enhance Unit Test Robustness and Code Quality

* **Date**: 2025-08-29
* **Services Affected**: `portfolio-common`, `position-valuation-calculator`

### 1. Summary (TL;DR)

A unit test for `PositionStateRepository.bulk_update_states` is failing due to an `AttributeError`, revealing a bug in how the number of updated rows is retrieved. Furthermore, our previous code review identified missing unit tests for critical logic in the `ValuationScheduler` (job dispatching) and `ValuationConsumer` (failure handling).

This RFC proposes to:
1.  **Fix the bug** in the `PositionStateRepository`.
2.  **Add the missing unit tests** to cover untested code paths and edge cases, improving our confidence in the system's reliability.

### 2. Motivation

A robust unit test suite is our first line of defense against regressions and production defects.
* **Correctness**: The current test failure indicates a code defect that must be fixed to ensure methods behave as expected.
* **Reliability**: The `ValuationScheduler` is a critical background component. Untested code paths, such as the actual dispatching of jobs to Kafka, represent a significant operational risk.
* **Completeness**: Explicitly testing all logical outcomes, including failure paths in consumers, ensures the system is resilient and behaves predictably under stress.

### 3. Proposed Technical Changes

#### 3.1. Fix `bulk_update_states` `AttributeError`

The method incorrectly attempts to access `.rowcount` on the `IteratorResult` object.

* **File to Modify**: `src/libs/portfolio-common/portfolio_common/position_state_repository.py`
* **Change**: Update the return statement to correctly access the row count from the underlying cursor result.

    * [cite_start]**From**: `return result.rowcount` [cite: 547]
    * **To**: `return result.rowcount`

#### 3.2. Add Unit Test for `ValuationScheduler` Job Dispatching

The scheduler's logic for claiming jobs is tested, but the final step of publishing them is not.

* **File to Modify**: `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
* **New Test**: `test_scheduler_dispatches_claimed_jobs`
    * **Logic**: This test will mock the `_dispatch_jobs` method's input (a list of `PortfolioValuationJob` objects). It will assert that the `KafkaProducer.publish_message` method is called the correct number of times. It will also inspect the `value` argument to ensure the `PortfolioValuationRequiredEvent` is created with the correct data (`portfolio_id`, `security_id`, `epoch`, etc.) from the job object.

#### 3.3. Add Unit Test for `ValuationConsumer` Failure Path

The consumer's "happy path" and `DataNotFoundError` path are tested, but the generic failure path is not.

* **File to Modify**: `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`
* **New Test**: `test_consumer_handles_unexpected_error`
    * **Logic**: This test will mock the `ValuationLogic.calculate_valuation` method to raise a generic `Exception`. It will assert that the `ValuationRepository.update_job_status` method is called with a status of `'FAILED'` and that the consumer's `_send_to_dlq_async` method is called exactly once.

### 4. Acceptance Criteria

* All 156 unit tests pass, including the currently failing `test_bulk_update_states`.
* New unit tests for the `ValuationScheduler` and `ValuationConsumer` are implemented and pass.
* Running the test suite with coverage shows an increase in coverage for `position_state_repository.py`, `valuation_scheduler.py`, and `valuation_consumer.py`.