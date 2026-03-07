# RFC-CA-MIXED-CONSIDERATION-01 Canonical Mixed Consideration Corporate Action Specification (Stock + Cash)

## 1. Document Metadata

* **Document ID:** RFC-CA-MIXED-CONSIDERATION-01
* **Title:** Canonical Mixed Consideration Corporate Action Specification (Stock + Cash)
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                              |
| ------- | ----- | ------ | -------------------------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical mixed consideration corporate action specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **Mixed Consideration Corporate Action** events in lotus-core, where:

* an event delivers **both**:

  * one or more **target securities**, and
  * one or more **cash consideration** amounts (often called “cash boot”)
* the source may be fully replaced or partially retained (but the defining feature here is **true cash consideration**, not just fractional cash-in-lieu)
* **cost basis must be allocated** between:

  * retained/received securities, and
  * the cash consideration component(s)
* any **realized P&L** (capital and FX) triggered by the cash consideration must be handled deterministically and auditable
* **position-level synthetic flows** (MVT-based) are recorded at product/position level for correct **position performance and contribution** analytics

**Important:** Position-level synthetic flows are **position-level only** and do not impact portfolio-level performance or portfolio cash. Real cash consideration is represented with real cash legs.

---

## 3. Scope

This RFC applies to corporate actions where upstream delivers:

* a security exchange/replacement (full or partial)
* and **true cash consideration** (not merely cash in lieu for fractions)

Examples include:

* merger with stock + cash consideration
* scheme of arrangement with mixed consideration
* mandatory exchange with a cash boot component
* reorganization delivering multiple targets plus cash

### 3.1 Transaction types covered by this RFC (child types)

This RFC standardizes the mixed-consideration overlays for both replacement categories:

**Security legs (reuse from other RFCs):**

* full replacement: `MERGER_OUT/MERGER_IN`, `EXCHANGE_OUT/EXCHANGE_IN`, `REPLACEMENT_OUT/REPLACEMENT_IN`
* partial transfer: `SPIN_OFF/SPIN_IN`, `DEMERGER_OUT/DEMERGER_IN` (when combined with cash boot)

**Cash consideration legs (introduced/standardized here):**

* `CASH_CONSIDERATION` (product/event-level cash component marker)
* `ADJUSTMENT` (cash instrument settlement leg)

**Fractional cash overlay (if present):**

* `CASH_IN_LIEU` (and its `ADJUSTMENT` cash leg)

**Optional:**

* `FEE`
* `TAX`

### 3.2 Out of scope

This RFC does not define:

* entitlement calculation logic (performed upstream)
* pure cash-in-lieu-only events (handled by other RFCs)
* tax law determination (policy-driven and/or upstream-driven)
* optional elections and election selection logic (resolved upstream)

---

## 4. Referenced Shared Standards

This RFC must be read together with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/16-position-level-synthetic-flows-for-corporate-actions.md`
* `shared/07-accounting-cash-and-linkage.md` (cash leg linkage and ADJUSTMENT rules)
* `RFC-CA-FULL-REPLACEMENT-01` (for full replacement security legs)
* `RFC-CA-PARTIAL-TRANSFER-01` (for partial transfer security legs)

---

## 5. Definitions

### 5.1 Cash consideration vs cash in lieu

* **Cash consideration (boot):** intentional cash component of the corporate action terms (e.g., “0.5 shares + USD 10 per share”).
* **Cash in lieu:** cash settlement only for fractional entitlements because whole units cannot be delivered.

These are separate components and must be modeled separately.

### 5.2 Mixed consideration event

An event that includes both:

* security delivery, and
* cash consideration

### 5.3 Basis allocation

Allocation of source basis across:

* received/retained securities
* cash consideration component(s)
* fractional cash in lieu component (if present)
* documented adjustments

### 5.4 Realized P&L in mixed consideration

Realized P&L may occur due to cash consideration.

Lotus-core must be able to represent realized P&L split into:

* `realized_capital_pnl`
* `realized_fx_pnl`
* `realized_total_pnl`

Whether realized P&L is recognized, and how, is policy-driven and/or upstream-driven.

---

## 6. Core Invariants

After completion:

* security legs (source/target) are processed according to their category RFC (full replacement or partial transfer)
* cash consideration is represented as a **real cash settlement** (cash leg)
* basis allocation reconciles across securities and cash components
* realized P&L for cash consideration is computed or accepted per policy
* position-level synthetic flows exist for security legs for position performance/contribution continuity

---

## 7. Parent Event Model

Every mixed consideration event must have a parent corporate action event.

### 7.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type`
* `processing_category = MIXED_CONSIDERATION`
* `event_status`
* `effective_date`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 7.2 Supported parent types (examples)

* `MERGER`
* `SCHEME_OF_ARRANGEMENT`
* `MANDATORY_EXCHANGE`
* `REORGANIZATION_MIXED`

---

## 8. Child Roles and Minimum Set

### 8.1 Canonical child roles

* security legs:

  * `SOURCE_POSITION_CLOSE` or `SOURCE_POSITION_REDUCE`
  * `TARGET_POSITION_ADD`
* cash consideration:

  * `CASH_CONSIDERATION`
* optional:

  * `CASH_IN_LIEU`
  * `CHARGE` (`FEE`)
  * `TAX`

### 8.2 Mandatory minimum child set

A valid mixed consideration event must include:

1. required security legs (as per category):

   * either full replacement (`*_OUT` + `*_IN`)
   * or partial transfer (source leg + one/many target legs)
2. at least one cash consideration marker/leg:

   * `CASH_CONSIDERATION` (product leg marker)
   * plus the corresponding cash settlement leg (`ADJUSTMENT`)

---

## 9. Required Orchestration Fields on Each Child

Each child must support:

* `parent_event_reference`
* `child_sequence_hint` (optional but recommended)
* `dependency_reference_ids` (recommended)
* `source_instrument_id`
* `target_instrument_id` (for security legs)
* `source_transaction_reference`
* `target_transaction_reference`

For cash consideration legs:

* `cash_consideration_reference_id` (recommended)
* `linked_cash_transaction_id` (recommended linkage from product marker to cash settlement)

---

## 10. Transaction Semantics

## 10.1 Security legs

Security legs must follow the applicable RFC:

* full replacement → `RFC-CA-FULL-REPLACEMENT-01`
* partial transfer → `RFC-CA-PARTIAL-TRANSFER-01`

Security legs must also emit position-level synthetic flows per shared/16.

## 10.2 Cash consideration marker (product leg)

`transaction_type = CASH_CONSIDERATION` represents the corporate action cash component.

It must:

* identify cash consideration amount and currency (local/base)
* identify whether it is per-share or total amount (recommended fields)
* identify settlement date/value date if provided
* carry basis allocation inputs for the cash component where upstream provides them
* be linkable to the cash settlement leg

This is a **corporate action child transaction** (not a deposit/withdrawal).

## 10.3 Cash settlement leg (cash instrument)

The actual cash movement must be represented as:

* `transaction_type = ADJUSTMENT`
* booked on the cash instrument (cash account)
* direction:

  * inflow for cash received
  * outflow for cash paid (rare, but possible)

The cash settlement leg must be linked to the `CASH_CONSIDERATION` marker via:

* same `economic_event_id`
* same `linked_transaction_group_id`
* `linked_cash_transaction_id`

---

## 11. Cost Basis Allocation Rules (Security + Cash)

### 11.1 Inputs expected from upstream

Upstream should provide at minimum:

* basis transferred out of source
* basis allocated into each target security
* basis allocated to cash consideration (if applicable)
* basis allocated to cash in lieu (if applicable)

Lotus-core must validate reconciliation but not compute entitlement.

### 11.2 Allocation reconciliation rule (mandatory)

Within tolerance:

`basis_out_of_source = Σ(basis_into_target_securities) + basis_allocated_to_cash_consideration + basis_allocated_to_cash_in_lieu + adjustments`

### 11.3 Default basis allocation fallback policy

If upstream does not provide explicit basis allocation to cash consideration:

* lotus-core must follow a configurable policy:

  * `REQUIRE_UPSTREAM_CASH_BASIS` (recommended default for correctness)
  * `ALLOCATE_PRO_RATA_BY_VALUE` (allowed only if customer approves)

---

## 12. Realized P&L Rules for Cash Consideration

Cash consideration may trigger realization depending on jurisdiction and bank policy.

Lotus-core must support three modes:

### 12.1 Mode A: Upstream provides realized P&L (recommended)

Upstream provides:

* `realized_capital_pnl`
* `realized_fx_pnl`
* `realized_total_pnl`

Lotus-core validates and stores.

### 12.2 Mode B: Lotus-core derives realized P&L from proceeds and allocated basis

If configured and sufficient data exists:

* `proceeds_local` = cash consideration amount
* `allocated_basis_local` = basis allocated to cash component
* `realized_capital_pnl_local = proceeds_local - allocated_basis_local`
* `realized_fx_pnl_local` derived if cross-currency and policy requires split
* base equivalents must be stored

### 12.3 Mode C: No realization recorded (policy exception)

Some banks may treat it as non-realizing for performance analytics; if so:

* realized P&L fields remain 0
* but basis allocation still must reconcile

Mode must be selected via policy:

* `cash_consideration_realization_mode = UPSTREAM | DERIVE | NONE`

---

## 13. Position-Level Synthetic Flows (Security Legs)

Security legs must emit position-level synthetic flows per shared/16.

### 13.1 Rule

* source leg synthetic outflow at MVT
* target leg synthetic inflow at MVT

### 13.2 Note

Cash consideration legs do not require synthetic flows by default, because they are real cash settlement events.

---

## 14. Cash-in-Lieu Overlay (Optional)

If fractional entitlements exist:

* model `CASH_IN_LIEU` as separate overlay
* include product leg + `ADJUSTMENT` cash leg
* allocate basis to fractional portion
* compute realized pnl for fractional portion per cash-in-lieu rules

Cash in lieu is always distinct from true cash consideration.

---

## 15. Processing Order and Dependencies

Default dependency-safe order:

1. register parent event
2. validate minimum child set
3. process security source leg
4. process security target leg(s)
5. finalize basis reconciliation for security legs
6. process `CASH_CONSIDERATION` marker (product leg)
7. process `ADJUSTMENT` cash settlement leg (cash instrument)
8. process `CASH_IN_LIEU` product leg(s) (if any)
9. process `ADJUSTMENT` cash-in-lieu cash leg(s) (if any)
10. process optional `FEE`
11. process optional `TAX`
12. mark event complete

Arrival order must not be assumed.

---

## 16. Event States

Required states:

* `PENDING_CHILDREN`
* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `PARKED`
* `FAILED`
* `COMPLETED`

Completion requires:

* security legs completed
* cash consideration cash settlement completed (or explicitly waived by policy)
* basis reconciled within tolerance
* any required realized P&L handling completed (or explicitly waived)
* overlays completed or waived

---

## 17. Idempotency and Replay

### 17.1 Parent idempotency key

Example:

* `(source_system, parent_event_reference, portfolio_id)`

### 17.2 Child idempotency key

* `(parent_event_reference, child_transaction_reference)`

### 17.3 Cash settlement idempotency key

* `(parent_event_reference, cash_consideration_reference_id)` for `ADJUSTMENT` settlement leg

Replays must not duplicate:

* security legs
* basis allocation effects
* cash posting
* realized P&L records
* overlays

---

## 18. Validation Rules

Must validate:

* parent exists and category matches
* required security legs exist
* `CASH_CONSIDERATION` marker exists
* cash settlement leg exists (unless policy allows upstream-late settlement)
* basis allocation reconciles
* realization mode satisfied (UPSTREAM/DERIVE/NONE)
* cash-in-lieu legs correctly separated from cash consideration
* linkage between marker and cash settlement is present

Hard-fail unless policy overrides:

* missing security legs
* missing cash settlement where required
* unreconcilable basis allocation mismatch
* missing realization inputs when mode requires them

---

## 19. Output Contract

Expose:

* parent event (type, category, status)
* security legs (source and target)
* synthetic flow details for security legs
* cash consideration marker (amounts, currency, dates)
* cash settlement leg (`ADJUSTMENT`)
* basis reconciliation summary across securities and cash
* realized P&L breakdown for cash consideration (if applicable)
* optional cash-in-lieu overlay details
* completion status

---

## 20. Worked Example: Merger with Stock + Cash

Client holds:

* 100 shares of `SRC`
* basis = USD 10,000

Upstream sends mixed consideration:

* receive 50 shares of `TGT`
* receive cash consideration USD 500
* basis allocation:

  * basis into `TGT` = 9,400
  * basis allocated to cash = 600
* prices at event:

  * `SRC` price = 100
  * `TGT` price = 200

### Security legs

* `MERGER_OUT` closes SRC, emits synthetic outflow at MVT
* `MERGER_IN` adds TGT, emits synthetic inflow at MVT

### Cash consideration

* `CASH_CONSIDERATION` marker: amount = 500
* `ADJUSTMENT` cash leg: +500 cash inflow
* realized capital pnl (derive mode):

  * 500 - 600 = -100

Event reconciles:

* 10,000 = 9,400 + 600

---

## 21. Test Matrix (Minimum)

* security legs process in correct order with synthetic flows
* cash consideration marker linked to cash settlement leg
* cash settlement affects cash balances correctly
* basis reconciles across security and cash components
* realization mode UPSTREAM and DERIVE both covered
* cash-in-lieu handled separately from cash consideration
* idempotency prevents duplicate cash posting
* event completion depends on required legs

---

## 22. Configurable Policies

Must be configurable and versioned:

* cash consideration realization mode (`UPSTREAM | DERIVE | NONE`)
* whether upstream must provide basis allocated to cash (`REQUIRE_UPSTREAM_CASH_BASIS`)
* price and FX sourcing policies (as per shared/16 and other CA RFCs)
* missing settlement behavior (park vs allow late)
* basis reconciliation tolerances
* dependency enforcement strictness
* idempotency strictness
* tax/fee posting expectations

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 23. Final Authoritative Statement

This RFC defines the canonical specification for **Mixed Consideration Corporate Actions** in lotus-core.

It standardizes:

* processing of security legs using existing CA transfer RFCs
* explicit modeling of **true cash consideration** using `CASH_CONSIDERATION` marker + `ADJUSTMENT` settlement leg
* basis allocation and reconciliation across securities and cash components
* optional realized P&L representation/derivation for cash consideration (capital + FX)
* strict separation of cash consideration from cash-in-lieu
* deterministic ordering, idempotency, replay safety, and operationally safe event states
