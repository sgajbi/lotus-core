# Developer's Guide: Cost Calculator

This guide provides developers with instructions for understanding, extending, and testing the `cost_calculator_service`.

## 1. Architecture Overview

The cost calculation logic is split into two distinct parts to ensure a clean separation of concerns:

* **`cost_calculator_service`:** This is the microservice itself. It owns both orchestration and the cost engine. The service contains the Kafka consumer, database repositories, and the logic for fetching, recalculating, and persisting cost state.
* **`app/cost_engine`:** This is the service-owned, pure cost-basis engine. It is stateless and knows nothing about Kafka or databases. It takes raw transaction data, processes it, and returns enriched transaction objects. Keeping it inside the owning service makes the deployment and ownership boundary explicit without sacrificing testability.

## 2. Adding Logic for a New Transaction Type

To add support for a new transaction type (e.g., a "GIFT_IN" of securities), follow these steps:

1.  **Update the Enum:** Add the new transaction type to the `TransactionType` enum in the cost engine.
    * **File:** `src/services/calculators/cost_calculator_service/app/cost_engine/domain/enums/transaction_type.py`

2.  **Create a New Strategy:** In the cost engine processing layer, create a new class that implements the `TransactionCostStrategy` protocol. This class will contain the specific business logic for your new transaction type.
    * **File:** `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`

    ```python
    class GiftInStrategy:
        def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
            # Logic to create a new cost lot, similar to TRANSFER_IN
            # ...
            pass
    ```

3.  **Register the Strategy:** In the `CostCalculator` class within the same file, add your new strategy to the `_strategies` dictionary in the constructor, mapping it to the enum value you created.

    ```python
    # In CostCalculator.__init__
    self._strategies: dict[TransactionType, TransactionCostStrategy] = {
        TransactionType.BUY: BuyStrategy(),
        TransactionType.SELL: SellStrategy(),
        # ... existing strategies
        TransactionType.GIFT_IN: GiftInStrategy(), # Add the new strategy here
    }
    ```

## 3. Testing

When adding new logic, ensure you also add corresponding tests:

* **Engine Logic:** Add unit tests for your new strategy's financial calculations in `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`.
* **Consumer Integration:** If necessary, add tests to `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py` to verify the consumer's orchestration of the new logic.
