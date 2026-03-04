# RFC 026: Refactor TWR Performance Engine for Maintainability and Performance

* **Status**: Proposed
* **Date**: 2025-09-01
* **Related RFCs**: RFC 025

## 1. Summary

This RFC proposes a targeted refactoring of the Time-Weighted Return (TWR) `performance-calculator-engine`. The current implementation, while functionally correct, is built on a complex, stateful, row-by-row iteration that is difficult to maintain and debug.

We will replace this iterative logic with a modern, vectorized implementation using the pandas library. This will be a **behaviorally identical refactor**, meaning the output must be bit-for-bit the same as the current engine. The goal is to significantly improve code clarity, maintainability, and likely performance, without altering the sophisticated, proprietary methodology. Additionally, we will enhance the `query_service` with specific metrics to improve the observability of our performance endpoints.

## 2. The Problem in Detail

The current TWR engine presents several challenges that constitute significant technical debt:

* **Maintainability Debt:** The core logic in `calculator.py` is a stateful `for` loop that processes a DataFrame one row at a time. It relies on opaque control flags (`NCTRL_1`, `PERF_RESET`) and temporary variables (`TEMP_LONG_CUM_ROR_PCT`) to manage state between iterations. This makes the code exceptionally difficult for new developers to understand, debug, or safely extend.
* **Performance Ceiling:** Row-wise iteration is a known anti-pattern in pandas that does not leverage the library's underlying C-speed optimizations. While performant enough for now, this approach will become a bottleneck as the length of time periods requested by users grows.
* **Monitoring Gap:** The performance endpoints in the `query_service` lack specific metrics. We cannot distinguish TWR vs. MWR latency or track which period types are most requested, creating a blind spot for usage patterns and performance tuning.

## 3. Proposed Solution

### 3.1. Core Principle: Behaviorally Identical Refactoring

The single most important constraint is that the **refactored engine must produce mathematically identical results to the existing one**. The unique logic for handling long/short sleeves and performance resets must be perfectly preserved. The existing test suite will be expanded to form a characterization suite to enforce this.

### 3.2. Vectorized Refactoring Plan

The project will be executed in three distinct phases:

**Phase 1: Characterization**
Create a comprehensive new test suite dedicated to the existing engine. This suite will capture its output for a wide range of complex edge cases, including:
* Portfolios with short positions (negative market value).
* Portfolios whose market value crosses zero.
* "Wipeout" scenarios that trigger the `PERF_RESET` logic.
This test suite will become the immutable benchmark against which the new implementation is validated.

**Phase 2: Vectorized Implementation**
The `calculate_performance` method will be rewritten to eliminate the `for` loop. The logic will be reimplemented using vectorized pandas and NumPy operations. For example:
* **Portfolio Sign:** `df['sign'] = np.sign(df['bod_market_value'] + df['bod_cashflow'])`
* **Reset Conditions:** The `PERF_RESET` conditions will be implemented using boolean masking and `df.shift()` to compare a row's values to the previous row's state.
* **Geometric Linking:** The cumulative return for contiguous periods (between resets) can be calculated by using `groupby()` on a column that identifies these periods, followed by a `cumprod()` on the daily return factors.

**Phase 3: Validation & Benchmarking**
The new vectorized implementation will be run against the characterization suite created in Phase 1. The output must match exactly. Performance benchmarks will be run to quantify the speed improvements.

### 3.3. Enhanced Monitoring

The `query_service` will be instrumented with new Prometheus metrics:
1.  **`twr_calculation_duration_seconds` (Histogram):** A new metric to specifically time TWR API requests.
2.  **`mwr_calculation_duration_seconds` (Histogram):** A new metric to specifically time MWR API requests.
3.  **`performance_period_type_requested_total` (Counter):** A new metric with a `period_type` label (e.g., "YTD", "EXPLICIT") to track usage patterns.

## 4. Acceptance Criteria

* The new `performance-calculator-engine` implementation produces results that are bit-for-bit identical to the original implementation across the entire characterization test suite.
* The `for` loop and all `NCTRL` variables are eliminated from `calculator.py`.
* Performance benchmarks demonstrate a measurable improvement in calculation speed for long time periods.
* The new Prometheus metrics are implemented in the `query_service` and exposed at the `/metrics` endpoint.