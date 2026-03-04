### **RFC 022: Enhance Cashflow Calculator Configurability and Monitoring**

  * **Status**: **Final**
  * **Date**: 2025-09-02
  * **Services Affected**: `cashflow_calculator_service`, `portfolio-common`
  * **Related RFCs**: None

-----

## 1\. Summary (TL;DR)

This RFC is approved. We will proceed with enhancing the `cashflow_calculator_service` to improve its flexibility and observability.

[cite\_start]The current implementation hardcodes its business logic in a Python dictionary (`cashflow_config.py`) [cite: 2121] and lacks specific business-level metrics. To address this, we will:

1.  **Externalize Business Logic**: The transaction-to-cashflow mapping rules will be moved from the static configuration file into a new `cashflow_rules` database table. The service will load these rules into an in-memory cache at startup to maintain high performance.
2.  **Enhance Monitoring**: A new Prometheus `Counter` metric, `cashflows_created_total`, will be introduced. It will be labeled by `classification` and `timing` to provide granular, business-level insight into the service's processing activity.

-----

## 2\. Decision

We will implement a new `cashflow_rules` table to act as the single source of truth for cashflow generation logic. The `CashflowCalculatorConsumer` will be refactored to query this table on startup, caching the rules for low-latency processing. We will also instrument the `CashflowLogic` class to emit the new `cashflows_created_total` metric, enriching our existing observability framework.

-----

## 3\. Architectural Consequences

### Pros:

  * **Business Agility**: The primary benefit is that cashflow rules can be modified by updating a database record, without requiring a developer to change code and redeploy the service. This empowers business analysts to manage financial logic directly.
  * **Improved Observability**: The new metric provides crucial, real-time insight into the business nature of the data flowing through the system, moving beyond purely technical monitoring (e.g., consumer lag) to answer questions like "How many dividend payments have we processed today?".
  * **Centralized & Auditable Logic**: Moving rules to the database provides a centralized, auditable source of truth for how transactions are treated.

### Cons / Trade-offs:

  * **Increased Startup Dependency**: The service will have a new dependency on the `cashflow_rules` table being populated to start correctly. This is a minor, acceptable trade-off.
  * **Performance Consideration**: The initial fetching of rules adds a small overhead at startup. However, by caching the rules in memory for the lifetime of the process, the per-message performance remains unaffected.

-----

## 4\. High-Level Design

### 4.1. Data Model Changes

An Alembic migration script will be created to add the following new table:

**New Table: `cashflow_rules`**
| Column | Type | Description |
| :--- | :--- | :--- |
| `transaction_type` | `VARCHAR(50)` (PK) | The transaction type (e.g., "BUY", "SELL", "FEE"). |
| `classification` | `VARCHAR(50)` | The financial purpose (e.g., "INCOME", "EXPENSE"). |
| `timing` | `VARCHAR(10)` | "BOD" or "EOD". |
| `is_position_flow` | `BOOLEAN` | True if it affects the instrument's value. |
| `is_portfolio_flow` | `BOOLEAN` | True if it's an external contribution/withdrawal. |
| `created_at` | `TIMESTAMPZ` | |
| `updated_at` | `TIMESTAMPZ` | |

### 4.2. Service Logic Changes

  * **New `CashflowRulesRepository`**: A new repository will be created in the `cashflow_calculator_service` to handle fetching all rules from the new table.
  * **Consumer Refactoring (`TransactionConsumer`)**:
      * On startup, the consumer manager will use the new repository to fetch all cashflow rules and load them into a singleton dictionary or a simple cache.
      * The `get_rule_for_transaction` function will now read from this in-memory cache instead of the static `CASHFLOW_CONFIG` object.
      * If a transaction is received for a type that has no rule in the cache, the consumer will log a critical error and send the message to the DLQ, as this is a non-retryable configuration error.

### 4.3. Monitoring

  * **New Metric**: A new `Counter` will be added to `portfolio-common/monitoring.py`:
    ```python
    CASHFLOWS_CREATED_TOTAL = Counter(
        "cashflows_created_total",
        "Total number of cashflows created, by classification and timing.",
        ["classification", "timing"]
    )
    ```
  * **Instrumentation**: The `CashflowLogic.calculate` method will be updated to increment this metric upon successful creation of a `Cashflow` object.

-----

## 5\. Implementation Plan

1.  **Phase 1: Database & Models**
      * Create an Alembic migration script for the new `cashflow_rules` table.
      * Add a corresponding `CashflowRule` model to `portfolio-common/database_models.py`.
2.  **Phase 2: Service Logic**
      * Implement the new `CashflowRulesRepository` in the `cashflow_calculator_service`.
      * Refactor the `ConsumerManager` and `TransactionConsumer` to load rules from the database into an in-memory cache at startup.
3.  **Phase 3: Observability**
      * Add the `CASHFLOWS_CREATED_TOTAL` metric to `portfolio-common/monitoring.py`.
      * Instrument the `CashflowLogic.calculate` method to increment the new metric.
4.  **Phase 4: Testing & Documentation**
      * Implement the full testing plan (see below).
      * Update all relevant documentation in `docs/features/cashflow_calculator/`.

-----

## 6\. Testing Plan

  * **Unit Tests**:
      * Create a new test file for the `CashflowRulesRepository` to verify its database query logic.
      * Update tests for `CashflowCalculatorConsumer` to mock the repository call and the in-memory cache, verifying it correctly handles both found and missing rules.
      * Update tests for `CashflowLogic` to assert that the `CASHFLOWS_CREATED_TOTAL` metric is incremented with the correct labels.
  * **Integration Tests**:
      * Create an integration test that seeds the test database with a rule, starts the consumer, and verifies that it successfully loads the rule into its cache.
  * **E2E Tests**:
      * The existing `test_cashflow_pipeline.py` will be run to ensure no regressions in the end-to-end flow.
      * A **new E2E test** will be created to validate the dynamic nature of the feature:
        1.  Ingest a transaction and verify it generates cashflow `X`.
        2.  **Directly update the rule** for that transaction type in the test database.
        3.  Manually trigger a reprocessing of the same transaction.
        4.  Verify that the system now generates the new, updated cashflow `Y` **without a service restart**.

-----

## 7\. Acceptance Criteria

1.  The `cashflow_rules` table is created via an Alembic migration.
2.  The `cashflow_calculator_service` loads its rules from the database at startup and caches them.
3.  The hardcoded `CASHFLOW_CONFIG` dictionary in `cashflow_config.py` is removed.
4.  The new `cashflows_created_total` Prometheus metric is implemented and correctly reports the classification and timing of generated cashflows.
5.  All new and modified logic is covered by unit, integration, and E2E tests as outlined in the testing plan.
6.  The documentation in `docs/features/cashflow_calculator/` is updated to reflect the new database-driven configuration and the availability of the new metrics in the operations guide.