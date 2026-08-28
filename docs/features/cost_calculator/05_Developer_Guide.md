# Developer's Guide: Cost Processing

This guide explains how cost-basis processing is structured and how to extend it.

Cost processing is not a separate deployment. It is a module inside the unified
`portfolio_transaction_processing_service` runtime, where cost, cashflow, and position effects
complete within one atomic use case.

## 1. Architecture Overview

The separation is between the pure calculation domain and the application layer that persists its
results:

* **Domain (`app/domain/cost_basis/`)** — stateless cost-basis calculation. It knows nothing about
  Kafka or the database. `calculation/cost_basis_strategies.py` holds the `CostBasisStrategy`
  protocol and its two implementations, `FIFOBasisStrategy` and `AverageCostBasisStrategy`.
* **Application (`app/application/cost_basis_processing/`)** — orchestration, lot-state
  persistence, disposal and basis-transfer persistence, and reconciliation.
  `timeline.py` selects the strategy for a portfolio and replays its cost timeline.
* **Delivery (`app/delivery/kafka/transaction_processing_consumer.py`)** — the consumer that drives
  the processing use case.

## 2. Two Different Extension Axes

The most common mistake is to conflate these. They are separate — and note that the two protocols
have deliberately similar names: `CostBasisStrategy` consumes lots for a cost-basis method, while
`TransactionCostStrategy` applies the economics of one transaction type.

### Adding a cost-basis method

Strategies are keyed by **cost-basis method**, not by transaction type. `CostBasisMethod`
(`src/libs/portfolio-common/portfolio_common/domain/cost_basis_method.py`) currently declares `FIFO`
and `AVCO`, and `timeline.py` chooses the matching strategy for the portfolio.

Adding a third method means adding an enum member, implementing the `CostBasisStrategy` protocol —
`add_buy_lot`, `consume_sell_quantity`, and the allocation-returning variant — and extending the
selection in `timeline.py`. This is a governed change: the method is persisted per portfolio and
affects realized P&L, so it needs an RFC and migration story, not just code.

### Adding a transaction type

This takes **three** edits, in different places. Doing only the first is the common failure: the
type registers cleanly and then fails at runtime.

**1. Declare the type.** Add a `_definition(...)` entry to `_REGISTRY` in
`src/libs/portfolio-common/portfolio_common/domain/transaction/type_registry.py`, declaring
`lifecycle_family`, `economic_role`, `position_effect`, `cash_effect`, `lot_behavior`, and
`settlement_behavior`. There is no `TransactionType` enum; types are string codes with declarative
definitions. `lot_behavior` governs how the application layer replays lots — see
`cost_basis_processing/calculation.py`, which reads it to choose incremental versus rebuild — but it
does **not** select the cost strategy.

**2. Map the type to a cost strategy.** `CostBasisCalculator.__init__`
(`app/domain/cost_basis/calculation/cost_basis_calculator.py`) holds
`_strategies: dict[str, TransactionCostStrategy]`, mapping each transaction-type code to a strategy
instance — `BuyStrategy`, `SellStrategy`, `SecurityInflowStrategy`, `RedemptionStrategy`,
`QuantityRestatementStrategy`, and so on. Add an entry for the new code, reusing an existing
strategy where the economics match rather than writing a new one by default.

`_resolve_strategy` applies these in order:

1. Rejects the transaction if `is_production_booking_transaction_type` is false, reporting the
   registry's `calculation_support_status`.
2. For cash instruments, returns `CashInflowStrategy` / `CashOutflowStrategy` for a fixed set of
   codes before consulting the map.
3. Otherwise looks up `_strategies`, and reports
   `No cost calculation strategy is registered for '<type>'` when the code is absent.

So a type that is production-bookable but unmapped fails at step 3. If the new type is a cash
instrument, check whether it also belongs in the step-2 branch.

**3. Add a cashflow rule.** Cost, cashflow, and position effects run in one atomic use case, so a
type that clears cost still fails if cashflow cannot resolve it.
`ProcessTransactionCashflowUseCase.process` resolves the type against `cashflow_rules` and raises
`TransactionProcessingError(reason_code="cashflow_rule_missing", retryable=False)` when no rule
exists. It is terminal, not retried, and it fails the whole transaction — the cost and position work
in the same use case does not stand. Insert the `cashflow_rules` row as described in
[the cashflow developer guide](../cashflow_calculator/05_Developer_Guide.md#2-adding-a-rule-for-a-new-transaction-type).

Step 3 is skippable only where `requires_cashflow_processing(transaction)` is false — the
non-cash FX contract lifecycle path, which returns before rule resolution. Everything else needs the
rule.

Use `calculation_support_status` and `production_booking_allowed` to introduce a type before its
calculation support is complete, rather than registering it as fully supported early.

## 3. Testing

```bash
pytest tests/unit/services/portfolio_transaction_processing_service/domain/cost_basis/
pytest tests/unit/services/portfolio_transaction_processing_service/delivery/kafka/test_transaction_consumer.py
```

Within the domain suite:

* `calculation/test_cost_basis_strategies.py` — per-strategy behaviour.
* `calculation/test_cost_calculator.py` — calculation entry point.
* `calculation/test_cost_basis_property_invariants.py` — property-based invariants that must hold
  for any strategy. A new cost-basis method should be added here, not only to its own test module.
* `calculation/test_disposal_allocation.py` and `calculation/test_basis_transfer_allocation.py` —
  allocation behaviour for disposals and transfers.
