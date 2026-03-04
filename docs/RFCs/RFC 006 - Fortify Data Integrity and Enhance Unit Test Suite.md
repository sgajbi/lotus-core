 
## RFC 006: Fortify Data Integrity and Enhance Unit Test Suite

* **Date**: 2025-08-29
* **Services Affected**: `portfolio-common`, `timeseries_generator_service`, `financial-calculator-engine`, `position_calculator`, `persistence_service`
* **Related RFCs**: RFC 005

### 1. Summary (TL;DR)

Our test suite is robust but currently reports **7 failures** and has several coverage gaps. The failures have uncovered two critical data integrity bugs related to `UPSERT` logic in the `timeseries_generator_service` and a `NULL` handling bug in the `OutboxDispatcher`. Other failures are due to minor test assertion mismatches and an outdated test database schema.

This RFC proposes a plan to:
1.  **Fix the critical data integrity bugs** to prevent data corruption.
2.  **Correct all 7 failing tests** to achieve a green build.
3.  **Add new unit tests** to close the coverage gaps identified in our prior review, improving long-term reliability.

### 2. Motivation

Achieving a consistently passing and comprehensive test suite is paramount for system stability and confident deployments. The primary motivations are:
* **Correctness**: We must fix the data integrity bugs in the `TimeseriesRepository` and `OutboxDispatcher` to prevent incorrect calculations and data loss in production.
* **Reliability**: A green test suite is our most important signal of system health. Correcting test failures and improving the test environment setup will make this signal reliable.
* **Completeness**: Closing the identified test coverage gaps will harden our system against future regressions in critical areas like dual-currency calculations and consumer retry logic.

### 3. Proposed Technical Changes

The work is broken down into three focused parts: fixing critical bugs, correcting failing tests, and adding new tests.

#### Part 1: Critical Bug Fixes (Data Integrity)

The following bugs were discovered by failing tests and must be addressed with high priority.

* **Issue**: The `UPSERT` logic in the `TimeseriesRepository` is incorrect. The `ON CONFLICT` clause for both `PositionTimeseries` and `PortfolioTimeseries` is missing the `epoch` column from its index elements. This will cause data corruption during reprocessing, as updates for a new epoch will overwrite records from the previous one instead of creating new versioned records.
    * **File to Modify**: `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`
    * [cite_start]**Change**: Update the `index_elements` in `on_conflict_do_update` to include `epoch` for both `upsert_position_timeseries` [cite: 5322-5323] [cite_start]and `upsert_portfolio_timeseries` [cite: 5326-5327].
* **Issue**: The `OutboxDispatcher` fails to increment the `retry_count` if its initial value is `NULL` in the database. The expression `OutboxEvent.retry_count + 1` results in `NULL` in PostgreSQL if the initial value is `NULL`.
    * **File to Modify**: `src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`
    * [cite_start]**Change**: Modify the `UPDATE` statement to use `func.coalesce(OutboxEvent.retry_count, 0) + 1` to ensure `NULL` values are treated as `0` before incrementing. [cite: 5456-5457]

#### Part 2: Test & Environment Corrections (Fixing Failures)

These changes address the remaining test failures.

* **Issue**: Minor assertion failures due to string formatting and floating-point precision.
    * **Files to Modify**:
        * `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_strategies.py`
        * `tests/unit/libs/performance-calculator-engine/test_calculator.py`
        * `tests/unit/libs/performance-calculator-engine/unit/test_helpers.py`
    * **Change**: Adjust the assertion string in `test_fifo_consume_sell_insufficient_quantity` to match the Decimal formatting. Widen the tolerance in `pytest.approx` for the performance calculator tests to resolve the minor precision discrepancies.
* **Issue**: Two integration tests are failing because the test database schema is out of date and is missing the `position_state` table.
    * **Files to Modify**: `tests/conftest.py`
    * **Change**: Enhance the `docker_services` fixture to ensure it waits for the `migration-runner` service to complete successfully *before* yielding control to the test session. This guarantees the test database schema is always fully up-to-date.

#### Part 3: New Unit Tests (Closing Coverage Gaps)

These new tests will cover the gaps identified in the previous review.

* **`financial-calculator-engine`**:
    * **File to Modify**: `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_strategies.py`
    * **New Test**: Add a test for `FIFOBasisStrategy` that involves a USD-based portfolio trading a EUR-denominated stock with changing FX rates to validate dual-currency cost basis and P&L calculations.
* **`position_calculator`**:
    * **File to Modify**: `tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py`
    * **New Test**: Add a test where `PositionCalculator.calculate` is mocked to raise an `Exception`, and assert that the consumer sends the message to the DLQ.
* **`persistence_service`**:
    * **File to Modify**: `tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py`
    * **New Test**: Add a test that mocks `repo.check_portfolio_exists` to return `False` initially, then `True`. Assert that `handle_persistence` raises `PortfolioNotFoundError` and that the consumer's retry mechanism is implicitly invoked, leading to an eventual success without using the DLQ.
* **`timeseries_generator_service`**:
    * **File to Modify**: `tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_portfolio_timeseries_logic.py`
    * **New Test**: Add a test where `repo.get_fx_rate` returns `None` and assert that `FxRateNotFoundError` is raised by the logic.
    * **File to Modify**: `tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
    * **New Test**: Add `test_upsert_position_timeseries` to mirror the existing test for the portfolio timeseries, ensuring the `ON CONFLICT` clause fix is explicitly tested.

### 4. Acceptance Criteria

* All 156 existing unit and integration tests must pass.
* The critical data integrity bugs in `TimeseriesRepository` and `OutboxDispatcher` are fixed.
* The new unit tests outlined in Part 3 are implemented and pass.
* The test suite runs without any failures, providing a reliable signal of system health.