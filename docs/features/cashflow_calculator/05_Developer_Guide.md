# Developer's Guide: Cashflow Calculator

This guide provides developers with instructions for understanding and extending the `cashflow_calculator_service`.

## 1. Architecture Overview

The `cashflow_calculator_service` is designed to be extremely simple and maintainable. It has two main parts:

* **`TransactionConsumer`:** The Kafka consumer that subscribes to `raw_transactions_completed` events. Its primary job is to look up the correct rule for the incoming transaction type and pass it to the logic layer.
* **`cashflow_rules` (Database Table):** This table contains the core of the service's business logic. It declaratively maps transaction types to their corresponding cash flow attributes. The consumer loads these rules into an in-memory cache at startup for high performance.

The philosophy of this service is to keep all business rules declarative and centralized in the database, making the system easy for business users to modify without code changes.

## 2. Adding a Rule for a New Transaction Type

To add support for a new transaction type (e.g., a "MANAGEMENT_FEE"), a new record must be inserted into the `cashflow_rules` table. This is an operational task, not a developer task, and does not require a code change or redeployment.

A developer's responsibility is to ensure the new transaction type exists in the system's enums and is handled correctly by upstream services.

1.  **Verify Transaction Type Enum:** Ensure the new transaction type exists in the shared enum.
    * **File:** `src/services/calculators/cost_calculator_service/app/cost_engine/domain/enums/transaction_type.py`

2.  **Add a Unit Test:** To ensure your new rule behaves as expected once added to the database, add a new test case to the logic test suite.
    * **File:** `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`

    ```python
    def test_calculate_management_fee_transaction(base_transaction_event: TransactionEvent):
        """A MANAGEMENT_FEE is a negative cashflow (outflow)."""
        event = base_transaction_event
        event.transaction_type = "MANAGEMENT_FEE"

        # Simulate the rule that will be in the database
        rule = CashflowRule(
            classification=CashflowClassification.EXPENSE,
            timing=CashflowTiming.EOD,
            is_position_flow=False, # Mgmt fees are not tied to a single position
            is_portfolio_flow=True   # It is an external outflow of capital
        )
        
        cashflow = CashflowLogic.calculate(event, rule)
        assert cashflow.amount < 0
        assert cashflow.is_position_flow is False
        assert cashflow.is_portfolio_flow is True
    ```

## 3. Testing

To run the unit tests specifically for the cashflow logic, use the following command from the project root:
```bash
pytest tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py