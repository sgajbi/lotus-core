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

The most common mistake is to conflate these. They are separate.

### Adding a cost-basis method

Strategies are keyed by **cost-basis method**, not by transaction type. `CostBasisMethod`
(`src/libs/portfolio-common/portfolio_common/domain/cost_basis_method.py`) currently declares `FIFO`
and `AVCO`, and `timeline.py` chooses the matching strategy for the portfolio.

Adding a third method means adding an enum member, implementing the `CostBasisStrategy` protocol —
`add_buy_lot`, `consume_sell_quantity`, and the allocation-returning variant — and extending the
selection in `timeline.py`. This is a governed change: the method is persisted per portfolio and
affects realized P&L, so it needs an RFC and migration story, not just code.

### Adding a transaction type

Transaction types do **not** get their own strategy class. They are declarative definitions in
`_REGISTRY` in `src/libs/portfolio-common/portfolio_common/domain/transaction/type_registry.py`.

Add a `_definition(...)` entry declaring `lifecycle_family`, `economic_role`, `position_effect`,
`cash_effect`, `lot_behavior`, and `settlement_behavior`. Cost treatment follows from
`lot_behavior` — for example `consume_lot` for a disposal, or `none` where no lot is affected. The
application layer reads that field; it does not branch on the type code.

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
