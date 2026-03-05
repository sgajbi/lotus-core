# shared/13-dual-leg-accounting-and-cash-adjustment-model.md

# Dual-Leg Accounting and Cash Adjustment Model

## 1. Purpose

This document defines the canonical dual-leg transaction model for lotus-core.

It standardizes how transactions with both:

* a **product / instrument effect**, and
* a **cash effect**

must be represented, linked, processed, and consumed downstream.

This document is a shared standard and must be referenced by all transaction RFCs that can produce a cash movement alongside a product-level effect.

---

## 2. Core Principle

Whenever a **position-level transaction** has a **cash impact**, it must be represented as a single economic event composed of **two linked transaction legs**:

1. **Product leg**
2. **Cash leg**

These two legs are different accounting representations of the same financial event and must always remain linked.

This is the default model for private-banking and wealth-tech transaction processing.

---

## 3. Scope of the Dual-Leg Model

## 3.1 Position-level transactions

A **position-level transaction** is a transaction whose primary business meaning is attached to a held instrument / security / product.

Examples:

* `BUY`
* `SELL`
* `DIVIDEND`
* `INTEREST`

If such a transaction has any cash impact, the dual-leg model is mandatory.

## 3.2 Portfolio-level transactions

A **portfolio-level transaction** is a transaction whose primary business meaning is attached directly to portfolio cash or portfolio-level movement rather than to a held security.

Examples:

* `DEPOSIT`
* `WITHDRAWAL`
* cash-only `TRANSFER_IN`
* cash-only `TRANSFER_OUT`

These are generally single-leg cash transactions unless another RFC explicitly defines otherwise.

---

## 4. Canonical Leg Types

## 4.1 Product leg

The **product leg** is recorded against the actual security / instrument / product that is the business subject of the transaction.

Examples:

* `BUY` against Apple equity
* `SELL` against Apple equity
* `DIVIDEND` against Apple equity
* `INTEREST` against a bond or interest-bearing source instrument

The product leg is the source of truth for:

* quantity changes
* lot creation / disposal
* cost basis changes
* held-since logic
* realized capital P&L
* realized FX P&L
* product-specific income semantics

## 4.2 Cash leg

The **cash leg** is recorded against the **cash instrument** corresponding to the impacted cash account.

The cash leg is the source of truth for:

* cash balance updates
* cash debits / credits
* settlement cash movement
* performance cash flow capture
* contribution / attribution cash-flow inputs
* cash-account-level ledger representation

---

## 5. Generic Cash-Leg Transaction Type

## 5.1 Canonical transaction type

The canonical generic transaction type for cash legs generated from position-level flows is:

* `ADJUSTMENT`

This transaction type is used only for the **cash leg** created or linked to a position-level economic event.

## 5.2 Why `ADJUSTMENT`

`ADJUSTMENT` is appropriate because the cash leg adjusts the balance of the cash instrument / cash account to reflect the economic effect of the product-level transaction.

It is generic enough to support:

* buy settlement cash outflow
* sell settlement cash inflow
* dividend cash inflow
* interest cash inflow / outflow

without creating separate cash transaction types for each business event.

## 5.3 Required clarification fields

Because `ADJUSTMENT` is intentionally generic, it must always carry metadata explaining *why* it exists.

At minimum, the cash leg must include:

* `originating_transaction_id`
* `originating_transaction_type`
* `adjustment_reason`
* `economic_event_id`
* `linked_transaction_group_id`
* `link_type`

Recommended `adjustment_reason` values:

* `BUY_SETTLEMENT`
* `SELL_SETTLEMENT`
* `DIVIDEND_SETTLEMENT`
* `INTEREST_SETTLEMENT`
* `INTEREST_CHARGE_SETTLEMENT`

`ADJUSTMENT` must never appear as an ambiguous standalone cash mutation without these fields.

---

## 5.4 Cash-leg amount and sign rule

For any dual-leg position-level transaction, the linked `ADJUSTMENT` cash leg must represent the **actual net cash movement** of the economic event.

### Mandatory rule

* the `ADJUSTMENT` cash leg amount must equal the **net cash amount**
* the `ADJUSTMENT` cash leg must use the **direction of the actual cash movement**
* the `ADJUSTMENT` cash leg must be the **opposite sign** of the product leg’s cash-impact representation

### Interpretation

If the product leg implies a cash outflow:

* the product leg carries the business-side expected settlement semantics
* the `ADJUSTMENT` cash leg carries the actual cash debit
* the `ADJUSTMENT` cash leg sign is opposite to the product leg’s cash-impact representation

If the product leg implies a cash inflow:

* the product leg carries the business-side expected receipt semantics
* the `ADJUSTMENT` cash leg carries the actual cash credit
* the `ADJUSTMENT` cash leg sign is opposite to the product leg’s cash-impact representation

### Canonical examples

* `BUY`

  * product leg expected cash impact: settlement cash required
  * cash leg: `ADJUSTMENT`
  * cash leg amount = net settlement cash
  * cash leg direction = cash outflow
  * cash leg sign = opposite to the product leg’s cash-impact representation

* `SELL`

  * product leg expected cash impact: net proceeds receivable
  * cash leg: `ADJUSTMENT`
  * cash leg amount = net proceeds
  * cash leg direction = cash inflow
  * cash leg sign = opposite to the product leg’s cash-impact representation

* `DIVIDEND`

  * product leg expected cash impact: net dividend receivable
  * cash leg: `ADJUSTMENT`
  * cash leg amount = net dividend
  * cash leg direction = cash inflow
  * cash leg sign = opposite to the product leg’s cash-impact representation

* `INTEREST`

  * product leg expected cash impact: net interest receivable or payable
  * cash leg: `ADJUSTMENT`
  * cash leg amount = net interest
  * cash leg direction = actual cash movement
  * cash leg sign = opposite to the product leg’s cash-impact representation

### Mandatory downstream rule

For downstream cash, performance, and contribution calculations:

* the `ADJUSTMENT` cash leg amount is the authoritative cash-flow amount
* that amount must be the **net amount**
* that amount must be interpreted in the **direction of the actual cash movement**


## 6. Required Linkage Model

## 6.1 Economic event linkage

Both legs must represent the same economic event and therefore must share:

* `economic_event_id`
* `linked_transaction_group_id`

## 6.2 Transaction linkage

The product leg and cash leg must be directly linkable through fields such as:

* `originating_transaction_id`
* `linked_cash_transaction_id`
* `link_type`
* `reconciliation_key`

## 6.3 Mandatory pairing rule

If a position-level transaction has a cash effect:

* a valid product leg without a corresponding linked cash leg is incomplete, unless explicitly parked pending external cash-leg arrival
* a valid cash leg without a corresponding product leg is incomplete, unless explicitly parked pending external product-leg arrival

---

## 7. Source-of-Truth Rule

## 7.1 Product leg ownership

The product leg owns:

* instrument-facing business meaning
* quantity and lot logic
* cost basis and holding-period logic
* realized P&L logic
* product-income semantics

## 7.2 Cash leg ownership

The cash leg owns:

* actual cash account mutation
* cash debit / credit amount
* cash flow event consumed by performance and contribution engines
* cash ledger balance movement

## 7.3 No double counting rule

A downstream system must not count the economic cash effect twice.

Therefore:

* the **cash leg** is the authoritative source for actual cash movement
* the **product leg** may carry expected or informative cash fields for validation / explainability
* the **product leg must not be the authoritative source for cash balance mutation** when a cash leg exists

This rule is mandatory.

---

## 8. Engine-Generated vs Upstream-Provided Cash Legs

## 8.1 Canonical behavior

The downstream business meaning is identical regardless of whether the cash leg is:

* generated by the engine, or
* provided by an upstream system

The system must treat both modes the same once both legs are linked.

## 8.2 Engine-generated mode

In engine-generated mode:

* the engine creates the `ADJUSTMENT` cash leg
* it populates all required linkage fields
* it applies the cash balance mutation

## 8.3 Upstream-provided mode

In upstream-provided mode:

* the upstream system provides the cash leg
* the system must link it to the product leg
* the cash leg must still conform to this shared model
* the system must prevent duplicate auto-generation

## 8.4 Canonical equivalence rule

Once linked, both modes must produce identical downstream semantics for:

* cash balances
* performance cash flows
* contribution inputs
* reporting
* reconciliation

---

## 9. Position-Level Transaction Rules

## 9.1 BUY

`BUY` is a product leg.

If cash is required for settlement:

* create / link an `ADJUSTMENT` cash leg
* product leg updates quantity / cost basis / lots
* cash leg reduces cash

## 9.2 SELL

`SELL` is a product leg.

If cash is received for settlement:

* create / link an `ADJUSTMENT` cash leg
* product leg reduces quantity / consumes lots / realizes P&L
* cash leg increases cash

## 9.3 DIVIDEND

`DIVIDEND` is a product leg.

If cash is received:

* create / link an `ADJUSTMENT` cash leg
* product leg records income semantics and tax decomposition
* cash leg increases cash

## 9.4 INTEREST

`INTEREST` is a product leg when tied to a position-level or instrument-level source.

If cash is received or paid:

* create / link an `ADJUSTMENT` cash leg
* product leg records interest income / expense semantics
* cash leg increases or decreases cash

---

## 10. Portfolio-Level Transaction Rules

## 10.1 Deposit / Withdrawal

`DEPOSIT` and `WITHDRAWAL` are cash-native portfolio-level transactions.

They contain only the **cash leg**.

They do not require a separate product leg.

## 10.2 Security Transfer In / Transfer Out

Security-only `TRANSFER_IN` and `TRANSFER_OUT` are product-only portfolio-level movements.

They contain only the **product leg**.

They do not require a cash leg unless a separate cash component explicitly exists.

## 10.3 Cash Transfer In / Transfer Out

Cash-only transfers contain only the **cash leg**.

They do not require a product leg.

---

## 11. Performance and Contribution Rule

For any position-level transaction with a cash impact:

* the **cash flow used in performance and contribution calculations must come from the cash leg**
* the product leg may retain expected-cash metadata for business explainability and reconciliation
* downstream performance engines must not synthesize a second cash flow from the product leg if a valid cash leg exists

This rule is mandatory to avoid double counting.

---

## 12. Canonical Data Requirements for Cash Legs

Every `ADJUSTMENT` cash leg must include at minimum:

* `transaction_id`
* `transaction_type = ADJUSTMENT`
* `cash_instrument_id`
* `cash_account_id`
* `movement_currency`
* `cash_amount_local`
* `cash_amount_base`
* `movement_direction`
* `effective_date`
* `value_date` where applicable
* `economic_event_id`
* `linked_transaction_group_id`
* `originating_transaction_id`
* `originating_transaction_type`
* `adjustment_reason`
* `link_type`
* `calculation_policy_id`
* `calculation_policy_version`

Recommended additional fields:

* `external_reference`
* `source_system`
* `reconciliation_key`
* `settlement_status`
* `cashflow_classification`

---

## 13. Required Downstream Behavior

Downstream systems must consume legs as follows:

* **Position engine** → product leg
* **Lot engine** → product leg
* **P&L engine** → product leg
* **Cash ledger** → cash leg
* **Performance engine** → cash leg for cash flows, product leg for non-cash product semantics
* **Reporting layer** → both legs, grouped by economic event
* **Reconciliation** → both legs, matched by linkage keys

---

## 14. Validation Requirements

The platform must validate:

* a required cash leg exists for every position-level transaction with cash impact
* linkage fields are populated and consistent
* no duplicate cash leg exists for the same economic event unless explicitly allowed
* cash-leg amount matches the expected economic effect of the product leg within configured tolerance
* downstream classification is consistent with `originating_transaction_type` and `adjustment_reason`

---

## 15. Idempotency and Replay Requirements

The dual-leg model must be replay-safe.

On replay:

* the product leg must not be duplicated
* the cash leg must not be duplicated
* linkage must remain stable
* event grouping must remain stable

Idempotency must be enforced at the **economic event** level, not only at the individual leg level.

---

## 16. Test Requirements

The shared test standard for the dual-leg model must cover:

* product leg + engine-generated cash leg
* product leg + upstream-provided cash leg
* missing cash leg for required dual-leg transaction
* duplicate cash leg prevention
* correct linkage population
* correct cash-leg source-of-truth behavior
* correct performance cash-flow sourcing from cash leg only
* replay-safe regeneration without duplication

---

## 17. Authoritative Rule for All Transaction RFCs

All transaction RFCs that can produce a product effect and a cash effect must reference this document.

Those RFCs must not redefine the dual-leg concept differently unless a superseding approved exception is documented.

This document is the shared source of truth for:

* dual accounting
* product leg vs cash leg ownership
* `ADJUSTMENT` cash-leg usage
* linkage requirements
* downstream consumption rules

---
