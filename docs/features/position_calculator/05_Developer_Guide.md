# Developer's Guide: Position Calculator

This guide provides developers with instructions for understanding and extending the `position_calculator_service`.

## 1. Architecture Overview

The `position_calculator_service` is a stateful consumer that builds an auditable trail of position history. Its architecture is straightforward:

* **`TransactionEventConsumer`:** The Kafka consumer that subscribes to `transactions.cost.processed` events. It is the main entry point and orchestrates the calls to the logic layer. It also contains the logic to check for stale epochs (epoch fencing).
* **`PositionLogic`:** A class that contains the core business logic for calculating the next position state based on an incoming transaction. It also houses the critical logic for detecting back-dated events and triggering the reprocessing flow.
* **`PositionRepository`:** Encapsulates all database queries for fetching historical data and saving new `position_history` records.

The primary design principle is that for any given transaction, the service recalculates the position history from that point forward, ensuring the timeline is always consistent.

## 2. Adding Logic for a New Transaction Type

If a new transaction type is introduced that needs to affect a position's quantity or cost basis, the logic must be added to the `calculate_next_position` method.

1.  **Locate the Method:** Open the core logic file.
    * **File:** `src/services/calculators/position_calculator/app/core/position_logic.py`

2.  **Add a New Condition:** Add an `elif` block to the `calculate_next_position` method to handle the new `transaction_type`. Modify the `quantity`, `cost_basis`, and `cost_basis_local` variables as required.

    ```python
    # In calculate_next_position method:

    elif txn_type == "STOCK_SPLIT":
        # Example: a 2-for-1 stock split
        # Quantity doubles, cost basis remains the same.
        quantity *= 2
        # No change to cost_basis or cost_basis_local
    ```

3.  **Add a Unit Test:** To ensure your new logic is correct, add a new test case to the logic test suite. This is a critical step.
    * **File:** `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`

    ```python
    def test_calculate_next_position_for_stock_split():
        initial_state = PositionStateDTO(quantity=Decimal("100"), cost_basis=Decimal("10000"))
        split_event = TransactionEvent(
            # ... populate with relevant data for a split ...
            transaction_type="STOCK_SPLIT",
            # ... other fields
        )
        new_state = PositionCalculator.calculate_next_position(initial_state, split_event)
        assert new_state.quantity == Decimal("200")
        assert new_state.cost_basis == Decimal("10000")
    ```

## 3. Testing

To run the unit tests specifically for the position logic, use the following command from the project root:
```bash
pytest tests/unit/services/calculators/position_calculator/core/test_position_logic.py