# Developer's Guide: Cashflow Processing

This guide explains how cashflow processing works and how to extend it.

Cashflow is not a separate deployment. It is a module inside the unified
`portfolio_transaction_processing_service` runtime, where cost, cashflow, and position effects
complete within one atomic use case.

## 1. Architecture Overview

Three pieces matter:

* **Transaction consumer** —
  `src/services/portfolio_transaction_processing_service/app/delivery/kafka/transaction_processing_consumer.py`
  subscribes to persisted transaction events and drives the processing use case.
* **`cashflow_rules` table** — the declarative rule set mapping a transaction type to its
  classification, timing, and aggregation level. It is loaded through
  `app/infrastructure/cashflow/rule_cache.py` rather than read per message. That cache is
  version-checked, not load-once: it refreshes on TTL expiry, on a source rule-set version change,
  or when a requested rule is missing, so a rule change takes effect without a restart.
* **Domain calculation** — `app/domain/cashflow/calculation.py` applies a resolved rule to one
  booked transaction. `app/application/cashflow_processing/use_case.py` orchestrates it.

The design intent is unchanged from when cashflow ran as its own service: business rules stay
declarative and centralized in the database, so adding a rule does not require a code change or a
redeployment. What changed is where the code runs.

## 2. Adding a Rule for a New Transaction Type

Adding the rule itself is an operational task — insert a record into `cashflow_rules`.

A developer's responsibility is to make sure the transaction type is known to the platform and
behaves correctly end to end.

1.  **Register the transaction type.** Types are declarative definitions, not enum members. Add a
    `_definition(...)` entry to `_REGISTRY` in
    `src/libs/portfolio-common/portfolio_common/domain/transaction/type_registry.py`, declaring at
    minimum `lifecycle_family`, `economic_role`, `position_effect`, `cash_effect`, `lot_behavior`,
    and `settlement_behavior`. These fields drive downstream treatment; they are not labels.

    **Registry registration alone is not enough for a production-bookable type.** Cost, cashflow,
    and position effects run in one atomic use case, and cost resolves a per-type strategy: a type
    absent from `CostBasisCalculator._strategies` fails with
    `No cost calculation strategy is registered for '<type>'`, so cashflow is never reached. Follow
    [the cost extension checklist](../cost_calculator/05_Developer_Guide.md#adding-a-transaction-type)
    for the full set of edits.

2.  **Add a unit test** for the rule's behaviour in
    `tests/unit/services/portfolio_transaction_processing_service/domain/cashflow/test_calculation.py`.

    The calculation entry point is `calculate_transaction_cashflow(transaction, rule, *, epoch=...,
    calculation_context=...)`, which takes a `BookedTransaction` and a `CashflowRule`
    (`classification`, `timing`, `is_position_flow`, `is_portfolio_flow`) and returns a
    `CalculatedCashflow`. `CashflowClassification` and `CashflowTiming` live in
    `app/domain/cashflow/types.py`. Follow the cases already in that test module rather than
    copying a snippet from this page — they carry the current fixtures and numeric policy.

3.  **Check settlement and transfer behaviour** if the type moves cash or lots between portfolios;
    `test_settlement_and_transfer_policy.py` in the same directory covers that boundary.

## 3. Testing

```bash
pytest tests/unit/services/portfolio_transaction_processing_service/domain/cashflow/
pytest tests/integration/services/portfolio_transaction_processing_service/test_cashflow_rule_contract.py
```

The integration test asserts the rule contract for the core business flows and the corporate-action
and rights transfer family, checking that each enumerated type has a rule with the expected
classification and flow level. It covers those families explicitly rather than every registered
type, so a new type outside them will not be caught there — add it to that test when its family
belongs under the contract.
