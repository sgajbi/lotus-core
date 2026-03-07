# RFC-CA-SPLIT-FAMILY-01 Canonical Stock Split, Reverse Split, and Consolidation Corporate Action Specification

## 1. Document Metadata

* **Document ID:** RFC-CA-SPLIT-FAMILY-01
* **Title:** Canonical Stock Split, Reverse Split, and Consolidation Corporate Action Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                      |
| ------- | ----- | ------ | -------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical split family specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **split-family corporate actions** in lotus-core, including:

* **Stock Split** (e.g., 2-for-1)
* **Reverse Split** (e.g., 1-for-10)
* **Consolidation** (economically same as reverse split)

These events:

* do **not** transfer economic exposure to a different instrument (same instrument continues)
* change **quantity** and **per-unit basis** while preserving total economic basis (subject to rounding)
* may produce **fractional entitlements** settled via **cash-in-lieu**
* must preserve lot and held-since continuity

**Important:** Split-family events are **same-instrument transformations**, not instrument-to-instrument transfers. Therefore, position-level synthetic flows for transfer continuity are **not required** by default.

---

## 3. Scope

This RFC applies to split-family events delivered by upstream systems as transactions to lotus-core, where upstream already determines:

* split ratio (numerator/denominator)
* eligible positions and quantity entitlement outcomes
* rounding rules and fractional settlement outcomes (if any)
* any cash-in-lieu proceeds and settlement dates (if any)

Lotus-core must process the resulting transactions to correctly calculate:

* positions
* cost basis
* cash legs (if cash-in-lieu exists)
* time series continuity
* realized P&L for cash-in-lieu fractional portion (policy-driven)

### 3.1 Transaction types covered by this RFC

* `SPLIT`
* `REVERSE_SPLIT`
* `CONSOLIDATION` (alias of reverse split; retained as explicit type if upstream provides it)
* overlay: `CASH_IN_LIEU`
* cash leg for cash-in-lieu: `ADJUSTMENT`
* optional: `FEE`, `TAX` (rare but possible)

### 3.2 Out of scope

This RFC does not define:

* entitlement calculation logic (performed upstream)
* instrument-to-instrument reorganizations (handled by other CA RFCs)
* rights issues
* bonus issues / stock dividends (handled in a separate RFC bundle)
* tax law determination

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/07-accounting-cash-and-linkage.md`
* `RFC-CA-REVERSAL-01` (for cancel/correct/rebook handling)

If fractional cash exists:

* `shared/16-position-level-synthetic-flows-for-corporate-actions.md` is relevant only for the `CASH_IN_LIEU` product leg semantics if you reuse the same overlay patterns (synthetic flows still optional).

---

## 5. Definitions

### 5.1 Split ratio

Represent split ratio as:

* `ratio_numerator` and `ratio_denominator`

Examples:

* 2-for-1 split: numerator=2, denominator=1
* 1-for-10 reverse split: numerator=1, denominator=10

### 5.2 Expected quantity transformation

Given original quantity `Q_old`:

`Q_new_raw = Q_old × ratio_numerator / ratio_denominator`

Then apply rounding rules to determine:

* `Q_new_deliverable` (whole units)
* `Q_fractional = Q_new_raw - Q_new_deliverable` (if any)

### 5.3 Basis conservation

Total basis should be preserved:

`basis_total_new = basis_total_old` (within tolerance)

Per-unit basis changes as quantity changes.

---

## 6. Core Invariants

After completion of a split-family event:

### 6.1 Quantity invariant

* position quantity changes from `Q_old` to `Q_new_deliverable`
* fractional portion is either:

  * carried as fractional units (if allowed by instrument policy), or
  * settled via cash-in-lieu (most common)

### 6.2 Basis invariant (mandatory)

Within tolerance:

* total cost basis remains unchanged **excluding** any basis allocated to a fractional portion settled in cash (if cash-in-lieu exists)

If no cash-in-lieu:

* `basis_total_new = basis_total_old`

If cash-in-lieu exists:

* `basis_total_new = basis_total_old - basis_allocated_to_fractional`
* and `basis_allocated_to_fractional` is used for cash-in-lieu realized P&L computation

### 6.3 Lot continuity invariant (mandatory)

* split-family events must preserve lot lineage and acquisition dates
* lots are transformed proportionally (quantity and per-unit basis), but remain linked to the original lots

### 6.4 No instrument-to-instrument transfer invariant

* `source_instrument_id == target_instrument_id` for the split action (same security continues)
* this is not a replacement/spin-off/exchange event

---

## 7. Parent Event Model

Every split-family event must be represented by a parent corporate action event.

### 7.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type` (`SPLIT`, `REVERSE_SPLIT`, or `CONSOLIDATION`)
* `processing_category = SAME_INSTRUMENT_TRANSFORM`
* `event_status`
* `effective_date`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 7.2 Recommended parent fields

* `ratio_numerator: int`
* `ratio_denominator: int`
* `rounding_mode` (upstream-provided) e.g. `FLOOR`, `ROUND`, `CEIL`, `MARKET_STANDARD`
* `fractional_handling` e.g. `CASH_IN_LIEU`, `ALLOW_FRACTIONAL`, `ROUND_DOWN_WITH_NO_COMP`

---

## 8. Child Roles, Minimum Set, and Linkage

### 8.1 Canonical child roles

* `SOURCE_POSITION_REDUCE` / `TARGET_POSITION_ADD` are not appropriate here because there is no source/target instrument.
* Use a specific role:

  * `SAME_INSTRUMENT_QUANTITY_RESTATE`

Overlays:

* `CASH_IN_LIEU`
* `CHARGE` (`FEE`)
* `TAX`

### 8.2 Mandatory minimum child set

A valid split-family event must include:

1. one split action child transaction (`SPLIT` or `REVERSE_SPLIT` or `CONSOLIDATION`)
   Optional:
2. `CASH_IN_LIEU` (+ `ADJUSTMENT`) if fractions exist
3. fees/taxes if posted separately

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

## 9.1 Split action (`SPLIT` / `REVERSE_SPLIT` / `CONSOLIDATION`)

Booked on the **same instrument**.

Must include:

* `ratio_numerator`
* `ratio_denominator`
* `quantity_before`
* `quantity_after_deliverable`
* `fractional_quantity` (if any; 0 if none or if not supported)
* optional `rounding_mode` if provided by upstream

### 9.1.1 Position effect

* `position_quantity_delta = quantity_after_deliverable - quantity_before`
* position remains open

### 9.1.2 Cost basis effect

If no cash-in-lieu:

* `cost_basis_total_after = cost_basis_total_before`
* `avg_cost_per_unit_after = cost_basis_total_after / quantity_after_deliverable`

If cash-in-lieu exists:

* basis allocation to fractional portion must be explicit or derived by policy (see Section 10)
* `cost_basis_total_after = cost_basis_total_before - basis_allocated_to_fractional`
* per-unit basis updated accordingly

### 9.1.3 No realized P&L by default

Split itself does not realize gains/losses.

Any realized P&L is only from cash-in-lieu fractional disposal if applicable.

---

## 10. Fractional Handling via Cash-in-Lieu (Optional Overlay)

If `fractional_quantity != 0` and fractional holdings are not supported, upstream will typically provide a cash-in-lieu component.

### 10.1 Cash-in-lieu structure

Cash-in-lieu must have:

1. a `CASH_IN_LIEU` product leg (fractional entitlement disposal economics)
2. an `ADJUSTMENT` cash leg (actual cash settlement)

### 10.2 Basis allocation to fractional portion (mandatory if cash-in-lieu exists)

The system must support:

* `basis_allocated_to_fractional` provided by upstream (preferred), or
* derived by policy, default:

  * `ALLOCATE_PRO_RATA_BY_QUANTITY` across the post-split raw quantity

Example policy formula:

`basis_allocated_to_fractional = cost_basis_total_before × (fractional_quantity / Q_new_raw)`

Policy must be configurable and versioned.

### 10.3 Realized P&L for cash-in-lieu (policy-driven)

If the institution recognizes realization on cash-in-lieu:

* `realized_capital_pnl = cash_proceeds - basis_allocated_to_fractional`
* FX split is handled if cross-currency, using standard realized FX model

If institution does not recognize realized P&L:

* realized pnl fields = 0
* but basis allocation still must be consistent and auditable

### 10.4 No double counting rule

* `ADJUSTMENT` cash leg affects cash balance only
* `CASH_IN_LIEU` product leg carries basis/pnl economics for position analytics
* split action child carries the quantity restatement and basis restatement

---

## 11. Lot and Held-Since Continuity (Mandatory)

### 11.1 Lot transformation rule

For each original lot `L_i`:

* `qty_i_after_raw = qty_i_before × ratio_numerator / ratio_denominator`
* apply rounding rules consistently across lots using a configurable lot-rounding policy

### 11.2 Lot rounding policy (configurable)

* `ROUND_AT_POSITION_LEVEL_THEN_ALLOCATE` (recommended default)
* `ROUND_PER_LOT` (rare; can cause reconciliation noise)

Recommended default approach:

1. compute total deliverable quantity at position level
2. allocate transformed quantities across lots proportionally
3. ensure sum(lot_qty_after) = deliverable quantity

### 11.3 Basis per lot

* lot total basis is preserved (unless fractional basis is allocated out, then allocate the reduction proportionally)
* per-unit basis adjusts based on new lot quantities

### 11.4 Held-since rule

* preserve acquisition date and held-since per lot (no reset)

---

## 12. Processing Order and Dependencies

Default dependency-safe order:

1. register parent event
2. process split action child (quantity/basis restatement)
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

* split action child applied
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

* quantity restatement
* lot restatement
* cash-in-lieu cash settlement
* basis allocation out to fractional

---

## 15. Validation Rules

Must validate:

* split ratio fields are present and valid (numerator > 0, denominator > 0)
* instrument identifiers are consistent (same instrument for source/target)
* quantity_after_deliverable consistent with ratio and rounding outcomes within tolerance
* lot transformation reconciliation holds:

  * sum(lot_qty_after) = position deliverable quantity
* basis conservation holds within tolerance
* if cash-in-lieu exists:

  * cash leg exists (or expected by policy)
  * basis allocated to fractional exists or can be derived by policy

Hard-fail unless policy override:

* missing ratio
* negative or zero denominator
* negative quantities
* unreconcilable quantity/basis mismatch beyond tolerance

---

## 16. Output Contract

Expose:

* parent event view (type, ratio, effective date, status)
* split action child view (quantity before/after, ratio, rounding metadata)
* updated position view
* updated lot view (before/after mapping)
* basis reconciliation summary
* cash-in-lieu overlay (product + cash legs) if present
* completion status

---

## 17. Worked Examples

### 17.1 Example A: 2-for-1 split (no cash-in-lieu)

* Q_before = 100
* ratio = 2/1
* Q_new_raw = 200
* Q_after_deliverable = 200
* basis_before = 10,000
* basis_after = 10,000
* avg_cost_before = 100
* avg_cost_after = 50

### 17.2 Example B: 1-for-10 reverse split with cash-in-lieu

* Q_before = 103
* ratio = 1/10
* Q_new_raw = 10.3
* Q_after_deliverable = 10
* fractional = 0.3 → cash-in-lieu
* basis_before = 10,300

Basis allocation (pro-rata by raw quantity):

* basis_fractional = 10,300 × (0.3 / 10.3) = 300 (example)
* basis_after = 10,300 - 300 = 10,000

Cash-in-lieu proceeds (upstream): 330

Realized pnl (if enabled):

* capital pnl = 330 - 300 = 30

---

## 18. Test Matrix (Minimum)

* 2-for-1 split updates quantity and halves per-unit basis (total basis constant)
* reverse split reduces quantity and increases per-unit basis (total basis constant)
* lot continuity preserved (acquisition dates unchanged)
* lot quantity reconciliation equals deliverable position quantity
* cash-in-lieu overlay creates product + ADJUSTMENT cash leg
* fractional basis allocation correct per policy
* cash-in-lieu realized pnl computed correctly (if enabled)
* replay/idempotency: applying same event twice does not duplicate effects
* reversal/correction tested via `RFC-CA-REVERSAL-01`

---

## 19. Configurable Policies

Must be configurable and versioned:

* rounding mode handling (if not supplied upstream)
* lot rounding policy (`ROUND_AT_POSITION_LEVEL_THEN_ALLOCATE` default)
* fractional handling (`CASH_IN_LIEU` vs `ALLOW_FRACTIONAL`)
* fractional basis allocation policy (require upstream vs derive)
* cash-in-lieu realization mode (`UPSTREAM | DERIVE | NONE`)
* reconciliation tolerances
* idempotency strictness

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 20. Final Authoritative Statement

This RFC defines the canonical specification for **Stock Split**, **Reverse Split**, and **Consolidation** corporate actions in lotus-core.

It standardizes:

* same-instrument quantity restatement
* basis conservation and per-unit basis adjustment
* lot and held-since continuity
* optional cash-in-lieu handling (product + cash legs) with basis allocation and optional realized P&L
* deterministic ordering, idempotency, and operationally safe event states

If any implementation or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
