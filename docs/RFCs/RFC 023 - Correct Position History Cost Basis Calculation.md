This is a critical data integrity bug fix. The proposal to align the `position_calculator_service` with the authoritative cost basis calculations from the `cost_calculator_service` is the correct approach. It establishes a single source of truth for cost basis logic, which is a foundational principle for a robust financial system.

The plan is approved. Proceed with producing the finalized RFC.

### **RFC 023: Correct Position History Cost Basis Calculation**

  * **Status**: **Final**
  * **Date**: 2025-09-02
  * **Lead**: Gemini Architect
  * **Services Affected**: `position_calculator_service`
  * **Related RFCs**: [RFC 001 - Epoch and Watermark-Based Reprocessing](https://www.google.com/search?q=docs/RFCs/RFC%2520001%2520-%2520Epoch%2520and%2520Watermark-Based%2520Reprocessing.md)

-----

### 1\. Summary (TL;DR)

This RFC finalizes the decision to correct a critical data integrity flaw in the `position_calculator_service`. The service currently uses an incorrect proportional approximation to calculate cost basis reductions for sell-side transactions, which is logically inconsistent with the precise, methodology-driven (e.g., FIFO) Cost of Goods Sold (COGS) calculated by the upstream `cost_calculator_service`.

We will refactor the `position_calculator_service` to use the authoritative `net_cost` and `net_cost_local` values provided on the incoming `TransactionEvent`. This change will eliminate the data drift, ensure the `position_history` table is verifiably correct, and simplify the system by removing redundant, flawed logic.

### 2\. Decision

We will implement the solution as proposed. The `calculate_next_position` method within `src/services/calculators/position_calculator/app/core/position_logic.py` will be refactored. For `SELL` and `TRANSFER_OUT` transactions, it will no longer use a proportional reduction. Instead, it will directly apply the `net_cost` (for base currency) and `net_cost_local` values from the inbound `TransactionEvent`, which correctly represent the cost of the shares being disposed of.

### 3\. Architectural Consequences

#### Pros:

  * **Correctness & Data Integrity**: This is the primary benefit. The `cost_basis` in the `position_history` table will now be perfectly consistent with the underlying FIFO or AVCO tax lots calculated upstream. This eliminates a significant source of data drift and ensures all downstream analytics and API responses are based on correct data.
  * **System Simplification**: The refactoring removes a redundant, complex, and incorrect calculation from the `position_calculator`, simplifying its logic. It enforces the principle of a single source of truth, where the `cost_calculator_service` is the sole authority on cost basis calculations.
  * **Improved Auditability**: The `position_history` table will become a more reliable and auditable record, as the change in cost basis after a sale will directly correspond to the COGS of that specific disposition.

#### Trade-offs:

  * **Tighter Coupling**: This change makes the `position_calculator_service` more tightly coupled to the correctness of the `net_cost` provided by the upstream `cost_calculator_service`. This is a desirable and necessary trade-off, as it enforces the single source of truth pattern for cost basis logic.

### 4\. High-Level Design

The change is confined to a single method in the `position_calculator_service`.

  * **File to Modify**: `src/services/calculators/position_calculator/app/core/position_logic.py`
  * **Method to Modify**: `calculate_next_position`

The logic for handling `SELL` and `TRANSFER_OUT` transaction types will be modified as follows:

**From (Incorrect Proportional Logic):**

```python
# OLD LOGIC - INCORRECT
elif txn_type in ["SELL", "TRANSFER_OUT"]:
    if not quantity.is_zero():
        proportion_of_holding = transaction.quantity / quantity
        cost_basis_reduction = cost_basis * proportion_of_holding
        cost_basis_local_reduction = cost_basis_local * proportion_of_holding
        
        cost_basis -= cost_basis_reduction
        cost_basis_local -= cost_basis_local_reduction
    
    quantity -= transaction.quantity
```

**To (Correct Additive Logic):**

```python
# NEW LOGIC - CORRECT
elif txn_type in ["SELL", "TRANSFER_OUT"]:
    quantity -= transaction.quantity

    # transaction.net_cost is negative for a SELL/TRANSFER_OUT, representing the COGS.
    # Adding this negative value correctly reduces the total cost basis.
    if transaction.net_cost is not None:
        cost_basis += transaction.net_cost
    if transaction.net_cost_local is not None:
        cost_basis_local += transaction.net_cost_local
```

### 5\. Testing Plan

A comprehensive testing strategy is required to validate this critical fix.

  * **Unit Tests**:

      * New unit tests will be added to `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`.
      * A specific test case will be created that:
        1.  Initializes a `PositionStateDTO` with a non-uniform average cost (e.g., quantity 100, cost basis 1200).
        2.  Creates a `SELL` `TransactionEvent` for a partial quantity (e.g., 50) with a `net_cost` derived from a different cost per share (e.g., `-550`, representing a FIFO cost of $11/share).
        3.  Calls `PositionCalculator.calculate_next_position`.
        4.  Asserts that the `new_state.cost_basis` is exactly `initial_state.cost_basis + event.net_cost` (i.e., `1200 + (-550) = 650`), and **not** the incorrect proportional value (`1200 * (1 - 50/100) = 600`).
      * A parallel test will be created to verify the logic for `net_cost_local`.

  * **End-to-End (E2E) Tests**:

      * Existing E2E tests, particularly `test_reprocessing_workflow.py`, `test_5_day_workflow.py`, and `test_dual_currency_workflow.py`, will be run to ensure no regressions. The final assertions on `cost_basis` and `realized_gain_loss` in these tests are the ultimate validation that the end-to-end pipeline is now consistent.

### 6\. Documentation Update

To ensure our documentation remains current and accurate, the following files must be updated as part of this change:

  * **`docs/features/position_calculator/01_Feature_Position_Calculator_Overview.md`**:

      * The "Gaps and Design Considerations" section detailing the flawed logic must be **removed**. The overview should now state that the service accurately tracks cost basis by consuming the authoritative COGS from the `cost_calculator_service`.

  * **`docs/features/position_calculator/03_Methodology_Guide.md`**:

      * The note about the "proportional approximation" flaw must be **removed**.
      * The table detailing the calculation logic must be updated to reflect the new, correct methodology for `SELL` and `TRANSFER_OUT` transactions, explaining that the cost basis is reduced by the `net_cost` from the transaction event.

### 7\. Acceptance Criteria

1.  The `calculate_next_position` logic in `position_logic.py` is refactored to use the additive `net_cost` and `net_cost_local` from the transaction event for sell-side dispositions.
2.  New unit tests are added to `test_position_logic.py` that specifically validate the correctness of the new cost basis calculation against a known expected value.
3.  All existing unit, integration, and E2E tests pass, with special attention to the final `cost_basis` assertions in `test_reprocessing_workflow.py` and `test_5_day_workflow.py`.
4.  The feature documentation in `docs/features/position_calculator/` is updated to remove all mentions of the previous flawed logic and accurately describe the new, correct methodology.