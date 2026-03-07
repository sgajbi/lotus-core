# RFC-CA-BONUS-STOCK-DIVIDEND-01 Canonical Bonus Issue and Stock Dividend Corporate Action Specification (Same-Line Equity Actions)

## 1. Document Metadata

* **Document ID:** RFC-CA-BONUS-STOCK-DIVIDEND-01
* **Title:** Canonical Bonus Issue and Stock Dividend Corporate Action Specification (Same-Line Equity Actions)
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                        |
| ------- | ----- | ------ | -------------------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical bonus issue and stock dividend specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **same-line equity corporate actions** in lotus-core, specifically:

* **Bonus Issue** (free shares issued pro-rata)
* **Stock Dividend** (dividend paid in additional shares of the same instrument)

These events:

* increase **quantity** of the same instrument (no instrument-to-instrument transfer)
* typically preserve **total cost basis** (per-unit basis decreases), unless policy/jurisdiction requires basis adjustments or accounting reclassification
* may include **fractional entitlements** settled via **cash-in-lieu**
* must preserve lot and held-since continuity

**Important:** These are **same-instrument actions** (unlike spin-offs/mergers). Therefore, position-level synthetic flows for transfer continuity are **not required** by default.

---

## 3. Scope

This RFC applies to bonus/stock-dividend events delivered by upstream systems to lotus-core, where upstream already determines:

* entitlement ratios (e.g., 1 bonus share for every 10 held)
* record date / ex-date / payment date (as provided)
* rounding rules and fractional outcomes
* cash-in-lieu proceeds and settlement (if fractional shares are not deliverable)
* any fees/taxes posted separately (rare)

Lotus-core must process these resulting transactions to correctly calculate:

* positions
* lots and held-since
* cost basis (total and per-unit)
* cash legs for cash-in-lieu (if any)
* time series continuity

### 3.1 Transaction types covered by this RFC

* `BONUS_ISSUE`
* `STOCK_DIVIDEND`
* overlay: `CASH_IN_LIEU`
* cash leg for cash-in-lieu: `ADJUSTMENT`
* optional: `FEE`, `TAX`

### 3.2 Out of scope

This RFC does not define:

* cash dividend (handled by `DIVIDEND` transaction RFC)
* rights issues (separate RFC)
* instrument-to-instrument reorganizations (other CA RFCs)
* entitlement calculation logic (upstream responsibility)
* tax law determination (policy-driven and/or upstream-driven)

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/07-accounting-cash-and-linkage.md`
* `RFC-CA-REVERSAL-01` (cancel/correct/rebook handling)

If fractional cash exists:

* `shared/16-position-level-synthetic-flows-for-corporate-actions.md` is relevant only if you reuse the `CASH_IN_LIEU` overlay structure; synthetic transfer flows are still not required for the main bonus/stock-dividend action.

---

## 5. Definitions

### 5.1 Bonus issue

A pro-rata issuance of additional shares of the same instrument for no cash payment.

### 5.2 Stock dividend

A dividend distributed in additional shares of the same instrument. Economically similar to a bonus issue, but may differ in accounting classification.

### 5.3 Entitlement ratio

Represent as:

* `ratio_numerator` and `ratio_denominator`

Examples:

* “1 share for every 10 held” → numerator=1, denominator=10
* “5% stock dividend” → numerator=5, denominator=100 (or upstream-provided explicit ratio)

### 5.4 Quantity outcomes

Given original quantity `Q_old`:

`Q_bonus_raw = Q_old × ratio_numerator / ratio_denominator`
`Q_new_raw = Q_old + Q_bonus_raw`

Then apply rounding/fraction rules to produce:

* `Q_bonus_deliverable` (whole shares)
* `Q_fractional` (if any)

---

## 6. Core Invariants

After completion:

### 6.1 Quantity invariant

* position quantity increases by `Q_bonus_deliverable`
* fractional portion is:

  * carried as fractional units if allowed, or
  * settled via cash-in-lieu

### 6.2 Basis invariant (default, policy-driven)

Default (common private banking approach):

* **total cost basis remains unchanged**
* per-unit basis decreases due to higher quantity

So:

* `basis_total_after = basis_total_before` (if no cash-in-lieu)
* `avg_cost_after = basis_total_after / quantity_after`

If cash-in-lieu exists:

* `basis_total_after = basis_total_before - basis_allocated_to_fractional`
* basis allocated to fractional is used to compute realized P&L if enabled

> Note: Some jurisdictions/accounting treatments may treat stock dividends differently (e.g., reclassification). This RFC supports policy-driven overrides while keeping the default conservative.

### 6.3 Lot continuity invariant

* lots must be preserved with acquisition dates intact
* bonus shares must be allocated into lots in a deterministic, auditable way

### 6.4 No instrument transfer invariant

* `source_instrument_id == target_instrument_id` (same security continues)
* this is not a replacement/spin-off/exchange event

---

## 7. Parent Event Model

Every bonus/stock-dividend event must be represented by a parent corporate action event.

### 7.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type` (`BONUS_ISSUE` or `STOCK_DIVIDEND`)
* `processing_category = SAME_INSTRUMENT_EQUITY_ISSUANCE`
* `event_status`
* `effective_date` (typically ex-date or payment date as provided by upstream)
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 7.2 Recommended parent fields

* `record_date`
* `ex_date`
* `pay_date`
* `ratio_numerator: int`
* `ratio_denominator: int`
* `rounding_mode`
* `fractional_handling` (`CASH_IN_LIEU`, `ALLOW_FRACTIONAL`, etc.)

---

## 8. Child Roles, Minimum Set, and Linkage

### 8.1 Canonical child roles

Main action role:

* `SAME_INSTRUMENT_QUANTITY_INCREASE`

Overlays:

* `CASH_IN_LIEU`
* `CHARGE` (`FEE`)
* `TAX`

### 8.2 Mandatory minimum child set

A valid event must include:

1. one main action child transaction (`BONUS_ISSUE` or `STOCK_DIVIDEND`)
   Optional:
2. `CASH_IN_LIEU` (+ `ADJUSTMENT`) if fractions exist
3. `FEE` and/or `TAX` if posted separately

### 8.3 Required orchestration/linkage fields

Each child must support:

* `parent_event_reference`
* `child_sequence_hint` (optional)
* `dependency_reference_ids` (recommended if overlays exist)
* `source_instrument_id` (same as target)
* `target_instrument_id` (same as source)
* `child_transaction_reference`

---

## 9. Transaction Semantics

## 9.1 Main action: `BONUS_ISSUE` / `STOCK_DIVIDEND`

Booked on the **same instrument**.

Must include:

* `ratio_numerator`
* `ratio_denominator`
* `quantity_before`
* `bonus_quantity_deliverable`
* `quantity_after_deliverable`
* `fractional_quantity` (if any)
* optional date fields: record/ex/pay dates as provided

### 9.1.1 Position effect

* `position_quantity_delta = bonus_quantity_deliverable`
* position remains open

### 9.1.2 Cost basis effect (default)

Default:

* `cost_basis_total_after = cost_basis_total_before`
* `avg_cost_after = cost_basis_total_after / quantity_after_deliverable`

If cash-in-lieu exists:

* reduce basis by allocated fractional basis (see Section 10)

### 9.1.3 Income classification (reporting)

Although called “stock dividend,” this is an equity issuance action.

By default:

* `income_classification = NONE` for the main action transaction
* downstream reporting may still label it as “stock dividend” based on `corporate_action_type`, not income classification

A policy may optionally mark it as income-like for reporting surfaces without treating it as a cash income.

---

## 10. Fractional Handling via Cash-in-Lieu (Optional Overlay)

If `fractional_quantity != 0` and fractional delivery is not supported, upstream will provide cash-in-lieu.

### 10.1 Structure

Cash-in-lieu must have:

1. a `CASH_IN_LIEU` product leg (fractional entitlement disposal economics)
2. an `ADJUSTMENT` cash leg (actual cash settlement)

### 10.2 Basis allocation to fractional portion (mandatory if cash-in-lieu exists)

Support:

* upstream-provided `basis_allocated_to_fractional` (preferred), or
* derived by policy, default:

  * `ALLOCATE_PRO_RATA_BY_QUANTITY` relative to the bonus entitlement

Example policy approach:

* allocate basis to fractional portion using proportional share of the *bonus shares* or of the *post-action quantity*, depending on policy.

This must be configurable and versioned.

### 10.3 Realized P&L for cash-in-lieu (policy-driven)

If enabled:

* `realized_capital_pnl = cash_proceeds - basis_allocated_to_fractional`
* FX split computed if cross-currency (standard realized FX model)

If disabled:

* realized pnl fields = 0
* basis allocation still must reconcile

### 10.4 No double counting rule

* `ADJUSTMENT` affects cash balance only
* `CASH_IN_LIEU` carries position economics (basis/pnl) for analytics

---

## 11. Lot and Held-Since Continuity (Mandatory)

### 11.1 Bonus allocation to lots (configurable)

Bonus shares must be allocated to lots deterministically.

Policies:

* `ALLOCATE_PRO_RATA_BY_LOT_QUANTITY` (recommended default)
* `ALLOCATE_TO_OLDEST_LOTS_FIRST`
* `ALLOCATE_NEW_SINGLE_LOT` (less preferred)

### 11.2 Lot reconciliation rule

* sum of bonus shares allocated across lots = `bonus_quantity_deliverable`
* sum of final lot quantities = `quantity_after_deliverable`

### 11.3 Basis per lot

Default:

* keep lot total basis unchanged (unless fractional basis is allocated out)
* per-unit basis adjusts downward as lot quantity increases

If fractional basis allocated out:

* reduce lot basis proportionally per policy

### 11.4 Held-since rule

* preserve acquisition date / held-since per lot (no reset)

---

## 12. Processing Order and Dependencies

Default order:

1. register parent event
2. process main action child (quantity increase + lot allocation + basis restatement)
3. if `CASH_IN_LIEU` exists:

   * process `CASH_IN_LIEU` product leg
   * process `ADJUSTMENT` cash leg
4. process optional `FEE`
5. process optional `TAX`
6. mark event complete

Arrival order must not be assumed.

---

## 13. Event States

Use the standard CA event states:

* `PENDING_CHILDREN`
* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `PARKED`
* `FAILED`
* `COMPLETED`

Completion requires:

* main action applied
* lot/basis reconciliation successful
* overlays processed or explicitly waived by policy

---

## 14. Idempotency and Replay

### 14.1 Parent idempotency key

Example:

* `(source_system, parent_event_reference, portfolio_id)`

### 14.2 Child idempotency key

* `(parent_event_reference, child_transaction_reference)`

Replays must not duplicate:

* bonus quantity increases
* lot allocations
* cash-in-lieu cash settlement
* fractional basis allocation

---

## 15. Validation Rules

Must validate:

* ratio fields valid (numerator ≥ 0, denominator > 0)
* quantity_after_deliverable = quantity_before + bonus_quantity_deliverable (within tolerance)
* lot allocation reconciles to deliverable bonus quantity
* basis invariants hold (per policy)
* if cash-in-lieu exists:

  * cash leg exists (or expected by policy)
  * basis allocated to fractional exists or can be derived by policy

Hard-fail unless policy override:

* missing ratio
* denominator ≤ 0
* negative quantities
* unreconcilable lot allocation mismatch beyond tolerance
* unreconcilable basis mismatch beyond tolerance

---

## 16. Output Contract

Expose:

* parent event (type, ratio, dates, status)
* main action child (quantity before/after, bonus qty, fractional qty)
* updated position view
* updated lot view (before/after mapping)
* basis reconciliation summary
* cash-in-lieu overlay (product + cash legs) if present
* completion status

---

## 17. Worked Examples

### 17.1 Example A: Bonus issue 1-for-10 (no cash-in-lieu)

* Q_before = 100
* ratio = 1/10
* bonus_raw = 10
* bonus_deliverable = 10
* Q_after = 110
* basis_before = 11,000
* basis_after = 11,000
* avg_cost_before = 110
* avg_cost_after = 100

### 17.2 Example B: Stock dividend 5% with cash-in-lieu

* Q_before = 103
* ratio = 5/100
* bonus_raw = 5.15
* bonus_deliverable = 5
* fractional = 0.15 → cash-in-lieu
* Q_after = 108
* basis_before = 10,300

Assume basis allocation to fractional derived (example):

* basis_fractional = 10,300 × (0.15 / 108.15) ≈ 14.29
* basis_after = 10,300 - 14.29 ≈ 10,285.71

Cash-in-lieu proceeds (upstream): 16.00
Realized pnl (if enabled):

* capital pnl = 16.00 - 14.29 = 1.71

---

## 18. Test Matrix (Minimum)

* bonus issue increases quantity and reduces per-unit cost (total basis constant)
* stock dividend increases quantity and preserves held-since/lot dates
* deterministic lot allocation policies covered
* lot reconciliation equals deliverable bonus quantity
* cash-in-lieu overlay creates product + ADJUSTMENT cash leg
* fractional basis allocation correct per policy
* cash-in-lieu realized pnl computed correctly if enabled
* replay/idempotency prevents double application
* reversal/correction tested via `RFC-CA-REVERSAL-01`

---

## 19. Configurable Policies

Must be configurable and versioned:

* rounding mode handling (if not supplied upstream)
* lot allocation policy for bonus shares
* fractional handling (`CASH_IN_LIEU` vs `ALLOW_FRACTIONAL`)
* fractional basis allocation policy (require upstream vs derive)
* cash-in-lieu realization mode (`UPSTREAM | DERIVE | NONE`)
* whether stock dividend is flagged income-like for reporting surfaces (without cash income)
* reconciliation tolerances
* idempotency strictness

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 20. Final Authoritative Statement

This RFC defines the canonical specification for **Bonus Issue** and **Stock Dividend** corporate actions in lotus-core.

It standardizes:

* same-instrument quantity increases
* basis conservation and per-unit basis adjustment (policy-driven)
* lot and held-since continuity with deterministic bonus allocation
* optional cash-in-lieu handling (product + cash legs) with fractional basis allocation and optional realized P&L
* deterministic ordering, idempotency, and operationally safe event states

If any implementation or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
