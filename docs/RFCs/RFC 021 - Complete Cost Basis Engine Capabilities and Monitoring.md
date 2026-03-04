# RFC 021: Complete Cost Basis Engine Capabilities and Monitoring

* **Status**: Final
* **Date**: 2025-09-02
* **Services Affected**: `cost_calculator_service`, `financial-calculator-engine`, `portfolio-common`, `persistence_service`

---
## 1. Summary

The `cost_calculator_service` and its underlying `financial-calculator-engine` are functioning correctly for the FIFO methodology. However, to be a gold-standard system, it must support other common cost basis methods and provide better visibility into its most performance-intensive operations.

This RFC finalizes the decision to implement two key enhancements:
1.  Fully implement the **Average Cost (AVCO)** basis methodology within the `financial-calculator-engine`, making it a selectable, portfolio-level strategy.
2.  Introduce new, specific Prometheus metrics to monitor the **depth** and **latency** of the full history recalculation process, our most computationally expensive operation.

---
## 2. Decision

We will proceed with the implementation as proposed. A new, nullable `cost_basis_method` column will be added to the `portfolios` table to allow clients to select their preferred accounting method, defaulting to `FIFO`. The `cost_calculator_service` will be refactored to use a strategy factory pattern, instantiating the correct cost basis logic (FIFO or AVCO) based on this portfolio-level configuration.

Furthermore, we will enhance observability by adding two new Prometheus Histogram metrics to the `financial-calculator-engine`'s `TransactionProcessor`, providing critical insights into the performance of historical recalculations.

---
## 3. Architectural Consequences

### Pros:
* **Increased Feature Completeness**: Supporting AVCO meets a wider range of client and jurisdictional accounting requirements, making the platform more versatile and commercially viable.
* **Enhanced Observability**: The new metrics will provide crucial data for diagnosing performance bottlenecks, planning capacity, and understanding the cost of back-dated transactions. This is critical for maintaining a scalable and reliable production environment.
* **Improved Maintainability & Extensibility**: The strategy pattern in the consumer is a clean architectural choice that makes it simple to add further cost basis methodologies in the future (e.g., LIFO, Specific Lot).

### Cons / Trade-offs:
* **Increased Complexity**: The introduction of the strategy factory adds a minor layer of complexity to the consumer logic.
* **Configuration Change Scope (v1)**: For this initial implementation, changing a portfolio's `cost_basis_method` will only affect transactions processed *after* the change. A full historical recalculation of the portfolio based on the new method is a more complex feature deferred to a future initiative.

---
## 4. High-Level Design

### 4.1. Data Model Changes
A new, nullable column will be added to the `portfolios` table.

* **Table**: `portfolios`
* **New Column**: `cost_basis_method`
* **Type**: `VARCHAR`
* **Default**: `FIFO`
* **Implementation**: An Alembic migration script will be created to add this column. The `Portfolio` model in `portfolio-common/database_models.py` and the corresponding `PortfolioEvent` will be updated. The `persistence_service` will be updated to handle this new optional field.

### 4.2. Engine Logic (`financial-calculator-engine`)
The core logic for the AVCO method will be implemented.

* **File**: `src/libs/financial-calculator-engine/src/logic/cost_basis_strategies.py`
* **Class**: `AverageCostBasisStrategy` will be fully implemented.
* **Logic**: The strategy must maintain a running state for each `(portfolio_id, security_id)` key, tracking:
    * `total_quantity`
    * `total_cost_local` (in the instrument's currency)
    * `total_cost_base` (in the portfolio's base currency)
* **`BUY` Event**: When a `BUY` occurs, the `quantity`, `net_cost_local`, and `net_cost` of the transaction are added to the running totals.
* **`SELL` Event**: When a `SELL` occurs, the Cost of Goods Sold (COGS) is calculated using the derived average cost per share (`total_cost / total_quantity`) for both local and base currencies. The running totals are then reduced accordingly.

### 4.3. Service Logic (`cost_calculator_service`)
The `CostCalculatorConsumer` will be updated to select the appropriate strategy dynamically.

* **File**: `src/services/calculators/cost_calculator_service/app/consumer.py`
* **Logic**:
    1.  Upon receiving a transaction event, the consumer will fetch the corresponding `Portfolio` record from the database.
    2.  Based on the value of the `cost_basis_method` field (defaulting to FIFO if NULL), it will instantiate either the `FIFOBasisStrategy` or the `AverageCostBasisStrategy`.
    3.  This strategy instance will be passed to the `DispositionEngine` for the scope of that transaction's processing.

### 4.4. Monitoring
Two new Prometheus Histogram metrics will be created and exposed.

* **File**: `src/libs/financial-calculator-engine/src/engine/transaction_processor.py`
* **Metrics**:
    1.  **`recalculation_depth`**:
        * **Type**: `Histogram`
        * **Description**: "Number of historical transactions replayed during a single cost basis recalculation."
        * **Implementation**: The value will be the count of all transactions (new and existing) being processed for a given key.
    2.  **`recalculation_duration_seconds`**:
        * **Type**: `Histogram`
        * **Description**: "Wall-clock time spent inside the core financial engine's recalculation process."
        * **Implementation**: The `TransactionProcessor.process_transactions` method will be timed, and the duration will be observed.

---
## 5. Testing Plan

* **Unit Tests**:
    * New, comprehensive unit tests will be created for the `AverageCostBasisStrategy`, including scenarios with multiple buys, partial sells, sell-outs, and complex dual-currency trades with fluctuating FX rates.
    * A new unit test will be added for the `CostCalculatorConsumer` to verify that the correct strategy is selected based on the portfolio's configuration.
* **E2E Tests**:
    * A new end-to-end test, `test_avco_workflow.py`, will be created. This test will:
        1.  Ingest a portfolio explicitly configured with the `AVCO` method.
        2.  Ingest a series of BUY transactions at different prices.
        3.  Ingest a SELL transaction.
        4.  Poll the `/transactions` endpoint and assert that the `realized_gain_loss` was calculated correctly according to the AVCO methodology.

---
## 6. Acceptance Criteria

1.  An Alembic migration for `portfolios.cost_basis_method` is created and successfully applied.
2.  The `AverageCostBasisStrategy` is fully implemented in the `financial-calculator-engine`, with 100% unit test coverage for its logic, including dual-currency scenarios.
3.  The `CostCalculatorConsumer` dynamically selects the cost basis strategy (FIFO or AVCO) based on the portfolio's `cost_basis_method` setting.
4.  The new Prometheus metrics, `recalculation_depth` and `recalculation_duration_seconds`, are implemented and exposed via the service's `/metrics` endpoint.
5.  A new end-to-end test (`test_avco_workflow.py`) is created and passes, validating the entire pipeline for the AVCO method.
6.  **Documentation in `docs/features/cost_calculator/` is updated**:
    * `01_Feature_Cost_Calculator_Overview.md` is updated to state that AVCO is now a supported, configurable method.
    * `03_Methodology_Guide.md` is updated with a new section detailing the AVCO calculation logic, especially for dual-currency trades.
    * `04_Operations_Troubleshooting_Guide.md` is updated to document the new `recalculation_depth` and `recalculation_duration_seconds` metrics, explaining what they measure and how to interpret them.