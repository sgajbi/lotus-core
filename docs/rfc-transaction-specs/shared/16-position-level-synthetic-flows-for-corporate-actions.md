# Position-Level Synthetic Flows for Corporate Action Performance and Contribution

## 1. Purpose

This document defines the canonical rules for **position-level synthetic flows** used by lotus-core to support correct **instrument/position-level performance and contribution** for corporate actions that move holdings from one instrument to another.

These synthetic flows are:

* recorded **only at product/position level**
* **not** cash-backed (no debit/credit legs)
* **do not** change cash balances
* **do not** affect portfolio-level funding or portfolio-level performance flows

They exist only to prevent misleading instrument-level analytics such as:

* source/parent position appearing as **100% loss** at close
* target/child position appearing as **100% gain** at open

This document is shared and must be referenced by all corporate action RFCs that include instrument-to-instrument transfers.

---

## 2. Scope

Applies to corporate action child transaction types that create instrument-to-instrument transfers, including:

* `MERGER_OUT` / `MERGER_IN`
* `EXCHANGE_OUT` / `EXCHANGE_IN`
* `REPLACEMENT_OUT` / `REPLACEMENT_IN`
* `SPIN_OFF` / `SPIN_IN`
* `DEMERGER_OUT` / `DEMERGER_IN`
* any transfer-style corporate action with a source and target instrument

Also applies to fractional settlement overlays:

* `CASH_IN_LIEU`

---

## 3. Non-Goals

This document does not define:

* entitlement calculation
* corporate action ratio logic
* portfolio-level TWR/MWR methodology
* cash ledger accounting
* dual-leg cash accounting (handled elsewhere)
* external funding flow classification (deposit/withdrawal)

---

## 4. Key Definitions

### 4.1 Market Value Transfer (MVT)

For a given instrument leg:

`MVT = price_at_event × quantity_at_event`

MVT is the valuation used to create synthetic flows.

### 4.2 Synthetic position flow

A synthetic position flow is an internal, non-cash flow recorded on a position leg to represent economic transfer of value between instruments.

### 4.3 Portfolio isolation rule

Synthetic position flows must not be consumed as portfolio-level flows. They are position-level only.

---

## 5. Core Principle

For any corporate action event that transfers economic exposure from a **source instrument** to a **target instrument**, lotus-core must create synthetic position flows such that:

* the source instrument shows a synthetic **outflow** at close/reduction
* the target instrument shows a synthetic **inflow** at open/increase

These flows are used only for:

* position-level performance
* position-level contribution analytics
* instrument-level time series continuity

---

## 6. Synthetic Flow Rules

## 6.1 Source-side rule (parent/source instrument)

When the source instrument is closed or reduced due to a corporate action:

* record a synthetic flow on the source leg:

`synthetic_flow_amount = - MVT_source`

Where:

* `MVT_source = source_price_at_event × source_quantity_removed_or_transferred`

## 6.2 Target-side rule (child/target instrument)

When the target instrument is created or increased due to a corporate action:

* record a synthetic flow on the target leg:

`synthetic_flow_amount = + MVT_target`

Where:

* `MVT_target = target_price_at_event × target_quantity_received`

## 6.3 Flow timing rule

Synthetic flows must be recorded on the **corporate action effective date** (or event trade date as provided upstream) consistently across source and target legs.

## 6.4 Valuation rule

Synthetic flows must use:

* `valuation_method = MVT_PRICE_X_QTY`

and must store the inputs:

* `quantity_used`
* `price_used`
* `currency_used`
* `fx_rate_to_base` (if required for base reporting)

## 6.5 Classification rule

Synthetic flows must be classified as position-level only, using a dedicated classification enum, for example:

* `synthetic_flow_classification = POSITION_TRANSFER_OUT` (source)
* `synthetic_flow_classification = POSITION_TRANSFER_IN` (target)

These must not map to external funding cashflow classifications.

---

## 7. Cash-in-Lieu Rules (Fractional Settlement)

Cash-in-lieu introduces **real cash movement** plus fractional economic disposal.

The event must be modeled such that:

* position-level performance remains correct
* real cash is not double-counted
* the fractional portion has correct cost and realized P&L

## 7.1 Cash-in-lieu child type

Use:

* `transaction_type = CASH_IN_LIEU`
* `child_role = CASH_IN_LIEU`

## 7.2 Required legs

For cash-in-lieu, there will be:

1. **product leg** representing fractional entitlement disposal
2. **cash leg** representing actual cash settlement

## 7.3 Product leg treatment

The cash-in-lieu product leg must include:

* `fractional_quantity`
* `fractional_valuation_amount` (MVT of fractional piece)
* `allocated_cost_basis_fractional`
* realized P&L breakdown:

  * `realized_capital_pnl`
  * `realized_fx_pnl`
  * `realized_total_pnl`

The product leg may also include a synthetic outflow classification specific to cash-in-lieu:

* `synthetic_flow_classification = POSITION_CASH_IN_LIEU_OUT` (optional but recommended)

## 7.4 Cash leg treatment

The cash leg must:

* post the actual cash settlement into the cash account
* follow the standard dual-leg cash rules (real cash)

## 7.5 No double-count rule

Position-level synthetic flows and real cash legs must be clearly separated:

* synthetic flows are for position performance/contribution only
* cash legs are for cash balance only

The system must ensure the analytics layer does not interpret the cash leg as a position-level synthetic flow, and does not interpret the synthetic flow as a portfolio-level cashflow.

---

## 8. Cost Basis Interaction

Synthetic flows are **not cost basis**.

Cost basis is transferred via corporate action basis rules.

However, synthetic flows must be generated in a way that is consistent with basis transfer sequencing:

* source basis transfer-out processed before target basis transfer-in finalization
* synthetic flows generated after quantities are known and before event completion

---

## 9. Required Data Model Additions

Every corporate action child transaction that can produce synthetic flows must support:

### 9.1 SyntheticFlowDetails (embedded model)

* `has_synthetic_flow: bool`
* `synthetic_flow_amount_local: Decimal`
* `synthetic_flow_amount_base: Decimal`
* `synthetic_flow_currency: str`
* `synthetic_flow_effective_date: date`
* `synthetic_flow_classification: SyntheticFlowClassification`
* `synthetic_flow_valuation_method: SyntheticFlowValuationMethod`
* `synthetic_flow_price_used: Decimal`
* `synthetic_flow_quantity_used: Decimal`
* `synthetic_flow_fx_rate_to_base: Decimal | None`
* `synthetic_flow_source: str` (e.g., `UPSTREAM_PROVIDED` or `DERIVED_IN_LOTUS_CORE`)

### 9.2 Recommended enums

* `SyntheticFlowClassification`:

  * `POSITION_TRANSFER_OUT`
  * `POSITION_TRANSFER_IN`
  * `POSITION_CASH_IN_LIEU_OUT`

* `SyntheticFlowValuationMethod`:

  * `MVT_PRICE_X_QTY`

---

## 10. Processing Order Rule

Synthetic flows must be generated only when the required dependency-safe state exists:

* parent event registered
* source and target quantities resolved
* fractional quantities resolved (if applicable)

Default ordering:

1. parent event
2. source-side child
3. target-side child
4. (optional) cash-in-lieu product + cash legs
5. generate synthetic flows (if not upstream-provided)
6. reconcile and mark event complete

---

## 11. Tests

Minimum tests required:

* source leg synthetic outflow generated at MVT
* target leg synthetic inflow generated at MVT
* synthetic flows do not affect cash balance
* synthetic flows are excluded from portfolio-level flow classification
* cash-in-lieu product and cash legs both exist
* cash-in-lieu basis allocated to fractional portion
* cash-in-lieu realized P&L computed correctly
* no double counting between synthetic flows and real cash leg
* dependency ordering enforced

---

## 12. Final Authoritative Statement

Position-level synthetic flows are mandatory for transfer-style corporate actions to support correct position-level performance and contribution.

They are:

* MVT-based (price × quantity at event)
* recorded only at product/position level
* excluded from portfolio-level performance and funding flows
* combined with explicit cash-in-lieu handling when real cash settlement exists

This document is the shared source of truth for these rules.
