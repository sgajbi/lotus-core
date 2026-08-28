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

This takes up to **eight** edits, in different places. Doing only the first is the common failure:
the type registers cleanly and then fails at runtime — or worse, books silently with the wrong result.

The recurring shape is that the registry declares *intent*, while several hard-coded maps must be
updated to match. The registry does not drive them, so nothing stops the two from disagreeing.

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

**2a. Extend redemption vocabulary and policy maps — required for a redemption-family type.**
Reusing `RedemptionStrategy` does not complete redemption support. The redemption economics
calculator accepts only codes in `REDEMPTION_TRANSACTION_TYPES` in
`app/domain/transaction/redemption/economics.py`, and command validation then indexes the
separate `REDEMPTION_ELIGIBLE_PRODUCT_TYPES_BY_TRANSACTION` map in
`app/domain/transaction/redemption/eligibility.py`. Add the new code to both maps when the type is
a redemption, with the eligible product types required by its policy. Otherwise cost processing
will reject the transaction as an unsupported redemption or fail with a missing eligibility
policy. Add economics and command-eligibility tests for the new code, including an ineligible
product case. This is conditional: non-redemption transaction families do not change these maps.

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

**4. Map the position effect — required whenever the type moves a holding.** If the registry
definition gives the type a `position_effect` other than `none`, it also needs a branch in
`_position_update_handler` in `app/domain/position/reducer.py`, which dispatches through hard-coded
type sets (`CASH_POSITION_DELTA_TRANSACTION_TYPES`, `POSITION_TRANSFER_TRANSACTION_TYPES`,
`SAME_INSTRUMENT_CORPORATE_ACTION_TYPES`, and the explicit `BUY` / `SELL` / redemption cases). Add
the code to the set that matches its economics, or add a handler if none fits, and cover it in the
reducer's domain tests.

**This step fails silently if skipped.** `_position_update_handler` returns `None` for an unknown
code, and `calculate_next_position_state` then returns `current_state` unchanged:

```python
next_state = (
    handler(current_state, transaction, txn_type) if handler is not None else current_state
)
```

There is no exception, log, or metric — unlike the cost and cashflow steps, which fail loudly. A
type that clears steps 1 to 3 but is missing here will book, pass processing, and write a
`position_history` row carrying no quantity or cost-basis effect. Verify the reducer branch with a
domain test rather than assuming a green pipeline means the type is wired up.

Use `calculation_support_status` and `production_booking_allowed` to introduce a type before its
calculation support is complete, rather than registering it as fully supported early.


**5. Add a settlement-cash resolver — required when the type generates its own cash leg.** If the
registry definition sets `settlement_behavior="requires_cash_leg"` (with a `trade`, `income`, or
`redemption` `lifecycle_family` and an `inflow`/`outflow` `cash_effect`), then
`production_transaction_types_for_generated_cash_legs()` includes the type automatically, and the
atomic use case will try to build its settlement leg.

That path calls `calculate_settlement_cash_movement()` in
`app/domain/transaction/settlement/cash_movement.py`, which looks the code up in the hard-coded
`_SETTLEMENT_CASH_RESOLVERS` map and raises
`ValueError("<type> has no ordinary settlement cash policy")` when it is absent. The transaction
fails while generating a leg the registry said it should have.

Note that `production_transaction_types_for_generated_cash_legs()` documents itself as returning
types "backed by a settlement-cash resolver", but it derives that set purely from registry fields —
nothing checks the resolver map. Registering the type is what opts it in; adding the resolver is a
separate edit you must make yourself. Cover it with the settlement domain tests.

**6. Set the cashflow value date — required when the cashflow should not use the transaction date.**
`_resolve_cashflow_date()` in `app/domain/cashflow/calculation.py` decides the persisted cashflow
date from two hard-coded sets, `_SETTLEMENT_DATED_TRANSACTION_TYPES` and
`_PAYMENT_DATED_TRANSACTION_TYPES`. Neither is derived from the registry or from
`_SETTLEMENT_CASH_RESOLVERS`, so a type wired through steps 1 to 5 is still absent from both.

**This step fails silently, like step 4.** The resolution order is: a
`synthetic_flow_effective_date` if present, then settlement date for a type in either set, then
settlement date for an `FX_BUY`/`FX_SELL` classification, and otherwise:

```python
return transaction.transaction_date.date()
```

A settlement-dated or payment-dated type that is missing from both sets is dated on its transaction
date instead. Nothing errors. Because cashflow timing feeds time-weighted return, the result is a
plausible but wrong performance figure rather than a failure — add a cashflow-date test alongside
the set update.


**7. Add manifest governance — required for a manifest-governed corporate-action type.** Parking and
release under a parent manifest are gated by their own vocabulary, not by the registry.
`corporate_action_manifest_child()` in
`app/domain/transaction/corporate_action/arrival.py` recognises a child only if its type is in
`MANIFEST_GOVERNED_CORPORATE_ACTION_TYPES`
(`corporate_action/classification.py`), and manifest validation dispatches through the closed cohort
policies in `corporate_action/cohort_policy.py` and the role and type maps in
`corporate_action/manifest.py`.

The two failure directions are worth separating:

* **Registered but not in the manifest vocabulary** — a transaction carrying parent-manifest
  identity is not recognised as a child, so it bypasses parking and is processed as an ordinary
  transaction. It books; it just skips the governance that was supposed to hold it.
* **Added to the vocabulary incompletely** — the type is recognised but has no matching cohort
  policy or role mapping, and manifest validation rejects it.

Add the type to the governed set, give it a cohort policy and role mapping, and cover both the
parking path and the release path in tests.


**8. Add redemption vocabulary and eligibility — required for a redemption-family type.** Reusing
`RedemptionStrategy` in step 2 is not enough. Two further maps gate the redemption path, and both
are hard-coded:

* `REDEMPTION_TRANSACTION_TYPES` in `app/domain/transaction/redemption/economics.py` —
  `_validated_inputs()` fails a code that is absent from it with
  `RedemptionCalculationReasonCode.INVALID_TRANSACTION_TYPE`.
* `REDEMPTION_ELIGIBLE_PRODUCT_TYPES_BY_TRANSACTION` in
  `app/domain/transaction/redemption/eligibility.py` —
  `assert_redemption_command_eligible()` **indexes** this dict directly, so a code present in the
  first map but missing here raises `KeyError` rather than a domain error.

Add the code to both, and cover the economics path and the eligibility path in tests.

> Worth knowing when you edit this: `REDEMPTION_TRANSACTION_TYPES` exists **twice** under different
> definitions. The ingestion copy in
> `src/services/ingestion_service/app/DTOs/transaction_model_dto.py` derives from the registry via
> `production_transaction_types_for_lifecycle_families("redemption")` and needs no edit. The
> processing copy above is a hard-coded frozenset and does. A redemption type added to the registry
> alone will pass ingestion validation and then fail in processing.

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
