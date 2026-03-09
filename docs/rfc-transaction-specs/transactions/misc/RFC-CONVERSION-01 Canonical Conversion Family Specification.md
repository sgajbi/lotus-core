# RFC-CONVERSION-01 Canonical Conversion Family Specification (Convertible Bond / Note → Equity, Warrants & Options Exercise


## 1. Document Metadata

* **Document ID:** RFC-CONVERSION-01
* **Title:** Canonical Conversion Family Specification (Convertible Bond / Note → Equity, Warrants & Options Exercise)
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                           |
| ------- | ----- | ------ | ------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical conversion family specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **conversion and exercise** events in lotus-core, including:

* **Convertible bond / note conversion** into equity
* **Warrant exercise** into equity
* **Listed option exercise** into underlying (equity)
  (cash-settled option expiry is out of scope and can be added later)

The goal is to support production-grade private banking / wealth-tech requirements:

* correct position transitions across instruments
* cost basis transfer and reconciliation
* cash settlement when exercise requires payment (strike) and/or cash-in-lieu
* realized P&L split into:

  * `realized_capital_pnl`
  * `realized_fx_pnl`
  * `realized_total_pnl`
* deterministic orchestration and processing order
* linkage between parent event and all child legs
* compatibility with corporate-action event processing patterns (parent + children)

---

## 3. Scope

This RFC applies when upstream systems send a set of transactions representing the **outcome** of a conversion/exercise decision, and lotus-core must process them to compute:

* positions
* cost basis
* cash flows (real cash only)
* income/expense classification where applicable
* time series and performance continuity

### 3.1 Out of scope

This RFC does not define:

* entitlement logic (conversion ratios, elections) — upstream responsibility
* option pricing/greeks/MTM — analytics layer responsibility
* margining/collateral
* cash-settled option payoff/expiry (separate RFC later)
* cancel/correct/rebook mechanics (handled by shared reversal model)

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/07-accounting-cash-and-linkage.md`
* `shared/08-timing-semantics.md`
* `shared/09-idempotency-replay-and-reprocessing.md`
* `shared/10-query-audit-and-observability.md`
* `shared/14-corporate-action-processing-model.md` (parent/child orchestration)
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/16-position-level-synthetic-flows-for-corporate-actions.md` (if synthetic flows required)
* `RFC-CA-REVERSAL-01`
* `RFC-BUY-01`, `RFC-SELL-01` (for lot and realized P&L structure)
* `RFC-FX-01` (if conversion/exercise involves FX or cross-currency cash legs)
* `RFC-CHARGE-01` (fees/taxes if posted separately)

---

## 5. Definitions

### 5.1 Source instrument vs target instrument

* **Source instrument:** instrument being converted/exercised out of (e.g., convertible bond, warrant, option)
* **Target instrument:** instrument received (e.g., equity shares)

### 5.2 Conversion vs exercise

* **Conversion:** convert a convertible bond/note into equity (often no strike cash payment, but may include cash-in-lieu)
* **Exercise:** pay strike to receive underlying (warrant/option) or receive cash (cash-settled; out of scope)

### 5.3 Cash components

Possible cash components in a conversion/exercise event:

* **strike payment** (cash outflow)
* **cash-in-lieu** for fractional shares (cash inflow, or outflow in rare cases)
* **fees/taxes** (cash outflow)

---

## 6. Canonical Transaction Types

### 6.1 Parent event type (grouping)

* `CONVERSION_EVENT` (parent corporate-action-like event)

### 6.2 Child transaction types (product legs)

Source legs:

* `CONVERSION_OUT` (convertible → equity)
* `EXERCISE_OUT` (warrant/option out)

Target legs:

* `CONVERSION_IN` (equity received)
* `EXERCISE_IN` (equity received)

Cash component markers (product-level, optional but recommended for audit):

* `STRIKE_PAYMENT` (if applicable)
* `CASH_IN_LIEU` (if fractional)
* optional: `FEE`, `TAX` (if posted as product legs per charge model)

Cash settlement legs:

* `ADJUSTMENT` (cash instrument)

> Note: For strike payments and cash-in-lieu, the **real cash movement** must be represented by `ADJUSTMENT` legs and linked to the corresponding product marker or the event.

---

## 7. Core Invariants

After completion:

* source position quantity decreases (often to zero for full conversion)
* target position quantity increases by delivered shares
* cost basis transfers from source to target per provided allocation (or deterministic policy where allowed)
* if strike payment exists, cash decreases by the strike amount
* if cash-in-lieu exists, cash increases by cash-in-lieu amount, and basis is allocated appropriately to fractional portion
* realized P&L fields are explicitly produced (even if zero), with capital vs FX split
* event is fully auditable and replay-safe

---

## 8. Parent Event Model

Every conversion/exercise must have a parent event record.

### 8.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type = CONVERSION_EVENT`
* `processing_category = CONVERSION_FAMILY`
* `event_status`
* `effective_date`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`
* `portfolio_id`

### 8.2 Recommended parent fields

* `source_instrument_id`
* `target_instrument_id`
* `conversion_ratio_numerator`, `conversion_ratio_denominator` (if provided)
* `fractional_handling` (`CASH_IN_LIEU`, `ALLOW_FRACTIONAL`)
* `strike_price` (if exercise)
* `strike_currency`
* `election_reference` / `instruction_id` (if relevant)

---

## 9. Child Roles, Minimum Sets, and Linkage

### 9.1 Required orchestration fields on each child

* `parent_event_reference`
* `child_transaction_reference` (unique within event)
* `child_sequence_hint` (recommended)
* `dependency_reference_ids` (recommended)
* `source_instrument_id`
* `target_instrument_id` (for IN legs)
* linkage: same `economic_event_id` and `linked_transaction_group_id`

### 9.2 Mandatory minimum child set

#### A) Convertible conversion (no strike)

1. `CONVERSION_OUT` (source reduction/close)
2. `CONVERSION_IN` (target add)

Optional overlays:

* `CASH_IN_LIEU` (+ `ADJUSTMENT`)
* `FEE`/`TAX`

#### B) Warrant/option exercise (with strike)

1. `EXERCISE_OUT`
2. `EXERCISE_IN`
3. `STRIKE_PAYMENT` marker (recommended)
4. `ADJUSTMENT` cash leg (strike cash outflow)

Optional overlays:

* `CASH_IN_LIEU` (+ `ADJUSTMENT`)
* `FEE`/`TAX`

---

## 10. Dual-Leg Rules for Cash Components

### 10.1 Strike payment

If a strike payment exists:

* product marker: `STRIKE_PAYMENT` (recommended)
* cash leg: `ADJUSTMENT` (cash outflow)

Cash leg must be linked by:

* same `economic_event_id`
* same `linked_transaction_group_id`
* explicit links:

  * `linked_product_transaction_id` on cash leg
  * `linked_cash_transaction_id` on product marker

### 10.2 Cash-in-lieu

If fractional shares settle in cash:

* product leg: `CASH_IN_LIEU`
* cash leg: `ADJUSTMENT` (cash inflow)

Must be handled exactly like other CA cash-in-lieu overlays:

* basis allocation to fractional portion is mandatory
* optional realized P&L on fractional portion is policy-driven
* no double counting between product and cash leg

---

## 11. Timing Semantics

### 11.1 Required dates

* `effective_date` (conversion/exercise date)
* `settlement_date` (cash value date; may match effective)
* optional `booking_date`

### 11.2 Timing policies

Configurable:

* `conversion_cash_effective_timing = SETTLEMENT_DATE | EFFECTIVE_DATE`
* `conversion_position_effective_timing = EFFECTIVE_DATE` (default, fixed)

---

## 12. Cost Basis Transfer Rules

### 12.1 Inputs expected from upstream (preferred)

Upstream should provide at minimum:

* `basis_out_of_source_local` (for the converted portion)
* `basis_into_target_local`
* if cash-in-lieu exists:

  * `basis_allocated_to_cash_in_lieu_local`

Reconciliation rule (within tolerance):

`basis_out_of_source_local = basis_into_target_local + basis_allocated_to_cash_in_lieu_local + adjustments`

### 12.2 Default basis transfer policy (fallback)

If upstream does not provide explicit basis allocation:

Configurable policy:

* `REQUIRE_UPSTREAM_BASIS` (recommended default)
* `ALLOCATE_PRO_RATA_BY_VALUE` (allowed only if client approves and pricing inputs exist)
* `ALLOCATE_PRO_RATA_BY_QUANTITY` (allowed only for certain jurisdictions/instruments)

### 12.3 Basis composition with strike

For exercise with strike payment:

Target basis must include strike payment (common approach):

`basis_into_target = basis_out_of_source + strike_cash_paid + includable_fees_taxes_in_basis`

Whether fees/taxes are includable is policy-driven.

---

## 13. Realized P&L Rules

Conversion/exercise is typically **not a sale**; many banks treat it as a basis transfer with **no realized capital P&L** at conversion time (unless cash components exist).

Lotus-core must support three modes:

`conversion_realization_mode = NONE | UPSTREAM_PROVIDED | DERIVE_FOR_CASH_COMPONENTS`

### 13.1 Default mode: NONE

* `realized_capital_pnl = 0`
* `realized_fx_pnl = 0`
* P&L recognition happens only when target is later sold, or via specific tax regime rules (outside scope)

### 13.2 Upstream-provided mode

* store realized pnl split as provided

### 13.3 Derive-for-cash-components mode (typical for cash-in-lieu)

* if cash-in-lieu exists:

  * realized capital pnl on the fractional disposal may be:

    * `cash_in_lieu_proceeds - basis_allocated_to_cash_in_lieu`
  * FX split computed per FX policy

In all modes, output fields must exist:

* local/base capital, fx, total

---

## 14. Position-Level Synthetic Flows (Optional)

Synthetic flows may be required for **position performance/contribution continuity**, especially when the conversion is treated as an instrument-to-instrument transfer with no explicit buy/sell cashflow at product level.

Policy:

* `conversion_synthetic_flow_mode = NONE | MVT_PRICE_X_QTY`

If enabled:

* source leg synthetic outflow at MVT on effective date
* target leg synthetic inflow at MVT on effective date
* synthetic flows are product-level only and must not impact portfolio cash.

Default: `MVT_PRICE_X_QTY` for conversions if your position performance model requires it (aligns with the CA transfer approach). Otherwise `NONE`.

---

## 15. Processing Order and Dependencies

Default dependency-safe order:

1. register parent event
2. process source product leg (`*_OUT`) — consume lots / reduce position
3. process target product leg (`*_IN`) — create lots / add position
4. reconcile basis transfer (and allocate to cash-in-lieu if present)
5. process strike payment marker (if present)
6. process strike cash `ADJUSTMENT` leg (if present)
7. process cash-in-lieu product leg and its cash `ADJUSTMENT` leg (if present)
8. process optional fee/tax legs
9. mark event complete

Arrival order must not be assumed.

---

## 16. Lot and Held-Since Rules

### 16.1 Target lots creation

Target equity shares delivered must create lots.

Held-since policy is configurable:

* `TARGET_HELD_SINCE_POLICY = DELIVERY_DATE | SOURCE_HELD_SINCE`

Default recommendation:

* `DELIVERY_DATE` for exercise (new acquisition)
* `SOURCE_HELD_SINCE` may be required for certain conversions (jurisdiction-dependent); must be explicit and auditable.

### 16.2 Basis allocation to lots

Allocate target basis across target lots proportionally to delivered quantities unless upstream provides lot-level basis.

---

## 17. Idempotency and Replay

### 17.1 Parent idempotency key

Example:

* `(source_system, parent_event_reference, portfolio_id)`

### 17.2 Child idempotency key

* `(parent_event_reference, child_transaction_reference)`

Replays must not duplicate:

* lot consumption/creation
* strike cash posting
* cash-in-lieu posting
* basis allocation

---

## 18. Validation Rules

Must validate:

* parent exists and category matches
* required child set exists for the chosen conversion type
* source position sufficient for conversion quantity (unless policy allows short)
* basis reconciliation holds within tolerance
* strike payment cash leg exists when strike is required
* cash-in-lieu legs are correctly linked and not double-counted

Hard-fail unless policy override:

* missing strike cash leg when strike required
* unreconcilable basis mismatch
* missing required OUT or IN leg

---

## 19. Output Contract

Expose:

* parent event view (type, dates, status, ids)
* source OUT leg (quantity delta, basis out)
* target IN leg (quantity delta, basis in, lots)
* cash components:

  * strike payment marker + cash leg
  * cash-in-lieu product leg + cash leg
* synthetic flow details (if enabled)
* realized P&L breakdown (capital vs FX, local + base)
* reconciliation summaries and audit metadata

---

## 20. Worked Examples

### 20.1 Convertible bond conversion (no strike), with cash-in-lieu

* Source: 10 units convertible note (basis 10,200)
* Conversion: receive 120 shares equity + fractional 0.5 share paid as cash-in-lieu 25
* Upstream basis allocation:

  * basis into equity: 10,150
  * basis to cash-in-lieu: 50

Process:

* `CONVERSION_OUT`: close/reduce note, basis out 10,200
* `CONVERSION_IN`: add 120 shares, basis in 10,150
* `CASH_IN_LIEU`: proceeds 25, basis 50 → realized capital pnl on fractional = -25 (if enabled for cash components)
* `ADJUSTMENT`: cash +25

### 20.2 Warrant exercise (strike payment)

* Source: 1,000 warrants (basis 2,000)
* Exercise: receive 1,000 shares at strike 5 USD → pay 5,000 USD
* Target basis (policy): 2,000 + 5,000 = 7,000

Process:

* `EXERCISE_OUT`: consume warrants, basis out 2,000
* `EXERCISE_IN`: add shares, basis in 7,000
* `STRIKE_PAYMENT` marker: 5,000
* `ADJUSTMENT`: cash -5,000

Realized P&L default: 0 (conversion_realization_mode NONE)

---

## 21. Test Matrix (Minimum)

* conversion without strike transfers basis correctly
* exercise with strike posts cash outflow and includes strike in basis (per policy)
* cash-in-lieu overlay creates product + cash legs and basis allocation; no double count
* synthetic flows (if enabled) create correct MVT-based product-level flows
* held-since policy applied correctly for target lots
* idempotency prevents duplicate postings
* missing dependency legs park or reject per policy
* reversal/correction handled via `RFC-CA-REVERSAL-01`

---

## 22. Configurable Policies

Must be configurable and versioned:

* `conversion_cash_effective_timing`
* `TARGET_HELD_SINCE_POLICY`
* `REQUIRE_UPSTREAM_BASIS` vs fallback allocation policies
* whether strike cash is included in target basis
* `conversion_realization_mode`
* `conversion_synthetic_flow_mode`
* reconciliation tolerances
* idempotency strictness

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 23. Final Authoritative Statement

This RFC defines the canonical specification for **Conversion/Exercise** processing in lotus-core, covering:

* convertible bond/note conversions to equity
* warrant/option exercises into underlying
* cash components (strike payment, cash-in-lieu) with proper linkage
* deterministic basis transfer and reconciliation
* explicit realized P&L structure (capital vs FX, local + base)
* optional synthetic flows for position performance continuity
* replay safety and operational robustness

If any implementation, test, or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
