# RFC-CA-MULTI-TARGET-01 Canonical Multi-Target Corporate Action Specification (One Source → Many Targets)

## 1. Document Metadata

* **Document ID:** RFC-CA-MULTI-TARGET-01
* **Title:** Canonical Multi-Target Corporate Action Specification (One Source → Many Targets)
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                       |
| ------- | ----- | ------ | ------------------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical multi-target corporate action specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **Multi-Target Corporate Action** events in lotus-core, where:

* one **source instrument** is mapped to **multiple target instruments**
* the event may be:

  * **partial transfer (source retained)** (most common, e.g., demerger into multiple entities), or
  * **full replacement (source extinguished)** with multiple resulting instruments
* **cost basis must be allocated** across all resulting target instruments (and possibly remaining source basis)
* **position-level synthetic flows** (MVT-based) are recorded at product/position level for correct **position performance and contribution** analytics
* optional **cash components** may exist:

  * `CASH_IN_LIEU` (fractional settlement)
  * true cash consideration (`CASH_CONSIDERATION`) if the multi-target event is mixed consideration

This RFC is focused on **orchestration, ordering, reconciliation, and determinism** for multi-target events.

**Important:** Position-level synthetic flows are **position-level only** and do not impact portfolio-level performance or portfolio cash.

---

## 3. Scope

This RFC applies to corporate actions that produce **multiple target securities** from one source, such as:

* demerger into 2+ companies
* restructuring creating multiple resulting lines (e.g., ordinary + stub/tracking + CVR)
* reclassification into multiple share classes where old line maps into more than one new instrument
* complex reorganizations producing multiple targets and optionally cash overlays

### 3.1 Transaction types covered (child types)

This RFC standardizes the multi-target pattern over these child transaction type families:

**Partial transfer families (source retained):**

* `DEMERGER_OUT` / `DEMERGER_IN`
* `SPIN_OFF` / `SPIN_IN` (when multiple targets exist; treated as multi-target spin-off)

**Full replacement families (source extinguished):**

* `REPLACEMENT_OUT` / `REPLACEMENT_IN` (multi-target replacement)
* `EXCHANGE_OUT` / `EXCHANGE_IN` (multi-target exchange)
* `MERGER_OUT` / `MERGER_IN` (multi-target merger delivery)

**Overlays:**

* `CASH_IN_LIEU` + `ADJUSTMENT` cash leg
* `CASH_CONSIDERATION` + `ADJUSTMENT` cash leg (if applicable)
* optional `FEE`, `TAX`

### 3.2 Out of scope

This RFC does not define:

* entitlement calculation logic (performed upstream)
* single-target events (covered by `RFC-CA-FULL-REPLACEMENT-01` and `RFC-CA-PARTIAL-TRANSFER-01`)
* tax law determination (policy-driven and/or upstream-driven)

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/16-position-level-synthetic-flows-for-corporate-actions.md`
* `shared/07-accounting-cash-and-linkage.md`
* `RFC-CA-FULL-REPLACEMENT-01` (when source extinguished)
* `RFC-CA-PARTIAL-TRANSFER-01` (when source retained)
* `RFC-CA-MIXED-CONSIDERATION-01` (if true cash consideration exists)

---

## 5. Definitions

### 5.1 Multi-target event

A corporate action event that results in:

* one source instrument, and
* N target instruments (N ≥ 2)

### 5.2 Allocation group

A logical grouping that ties all target legs (and any related cash components) into a single basis allocation context.

### 5.3 Result set

The complete set of child transactions required to represent the event, including:

* source leg
* target legs (N)
* basis allocation outcomes
* overlays (cash in lieu, cash consideration)
* charges/taxes

---

## 6. Core Invariants

After completion:

### 6.1 Target completeness invariant

All required target legs must be present and processed.

No event may be marked complete if any required target is missing or pending.

### 6.2 Basis conservation invariant (mandatory)

Within tolerance:

If source retained:

`original_source_basis = remaining_source_basis + Σ(basis_target_i) + basis_cash_in_lieu + basis_cash_consideration + adjustments`

If source extinguished:

`basis_out_of_source = Σ(basis_target_i) + basis_cash_in_lieu + basis_cash_consideration + adjustments`

### 6.3 Deterministic target ordering invariant

Processing order must be deterministic even when multiple targets exist.

### 6.4 Portfolio isolation invariant

Position-level synthetic flows:

* must not affect cash balances
* must not be treated as portfolio funding flows
* must be used only for position-level performance and contribution

---

## 7. Parent Event Model

Every multi-target event must have a parent corporate action event.

### 7.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type`
* `processing_category = MULTI_TARGET_TRANSFER`
* `event_status`
* `effective_date`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 7.2 Recommended parent fields

* `allocation_group_id` (stable id to bind all targets)
* `is_source_retained: bool`
* `expected_target_count: int`
* `expected_cash_components: set` (e.g., `{CASH_IN_LIEU, CASH_CONSIDERATION}`)

---

## 8. Child Roles and Minimum Set

### 8.1 Canonical child roles

* `SOURCE_POSITION_CLOSE` or `SOURCE_POSITION_REDUCE` (depends on source retained vs extinguished)
* `TARGET_POSITION_ADD` (N targets)
* logical `COST_BASIS_REALLOCATE`
* optional `CASH_IN_LIEU`
* optional `CASH_CONSIDERATION`
* optional `CHARGE` (`FEE`)
* optional `TAX`

### 8.2 Mandatory minimum child set

A valid multi-target event must include:

1. exactly one source leg per source economic line
2. at least two target legs (`TARGET_POSITION_ADD`)
3. enough basis allocation information to reconcile across all targets and overlays

---

## 9. Required Orchestration / Linkage Fields

Each child must support:

* `parent_event_reference`
* `child_sequence_hint` (optional but recommended)
* `dependency_reference_ids` (recommended)
* `source_instrument_id`
* `target_instrument_id` (mandatory for target legs)
* `source_transaction_reference`
* `target_transaction_reference`

### 9.1 Multi-target specific linkage fields (required)

Each target leg must include:

* `allocation_group_id` (same for all target legs in the event)
* `target_leg_index: int` (1..N, stable)
* `target_leg_role_code: str` (optional but recommended, e.g., `NEWCO_A`, `NEWCO_B`, `STUB`, `CVR`)

### 9.2 Deterministic ordering rule

When multiple targets are ready, lotus-core must order target processing by:

1. `target_leg_index` if present
2. else stable lexicographic order of `target_instrument_id`
3. else stable lexicographic order of `child_transaction_reference`

This rule must be consistent across replays.

---

## 10. Transaction Semantics

Multi-target semantics extend the base RFCs:

### 10.1 Source retained vs source extinguished

The parent must specify whether the source is retained.

* If retained: apply `RFC-CA-PARTIAL-TRANSFER-01` semantics for the source leg.
* If extinguished: apply `RFC-CA-FULL-REPLACEMENT-01` semantics for the source leg.

### 10.2 Target legs (N targets)

Each target leg is a `TARGET_POSITION_ADD` and must:

* add quantity for its target instrument
* assign basis for that target leg
* emit position-level synthetic inflow at MVT (shared/16)

### 10.3 Source synthetic flow

Source leg must emit synthetic outflow at MVT (shared/16), with the quantity mode per applicable RFC and policy.

---

## 11. Position-Level Synthetic Flows (Mandatory)

All security legs (source and each target) must emit synthetic flows per `shared/16`.

### 11.1 Source synthetic outflow

* classification: `POSITION_TRANSFER_OUT`
* amount: `-(price_source × qty_reference)`

### 11.2 Target synthetic inflows (N)

For each target i:

* classification: `POSITION_TRANSFER_IN`
* amount: `+(price_target_i × qty_target_i)`

### 11.3 Pricing/FX

Pricing and FX sourcing and missing-data behavior must follow shared/16 and the applicable base RFC.

---

## 12. Cost Basis Allocation Rules (Multi-Target)

### 12.1 Required upstream basis inputs

Upstream must provide either:

* basis allocated per target leg, and remaining source basis (if retained), or
* basis transferred out plus per-target basis allocations plus overlays, sufficient to reconcile

### 12.2 Basis reconciliation rule (mandatory)

Within tolerance, reconcile as per Section 6.2.

### 12.3 Allocation visibility requirement

The system must expose a basis allocation table per event:

* source basis original
* remaining source basis (if retained)
* basis per target leg (N rows)
* basis allocated to cash in lieu (if any)
* basis allocated to cash consideration (if any)
* adjustments

### 12.4 Lot-level mapping requirement

The platform must support an auditable mapping:

* from source lots to target lots (possibly many-to-many)

If upstream provides lot-level allocation, preserve it.

If not, allocate via policy (same policies as Partial Transfer RFC), but totals must match upstream totals.

---

## 13. Lot and Held-Since Continuity

### 13.1 Source retained

* source lots remain, but their basis reduces per allocation

### 13.2 Targets

* create target lots with linkage back to source lots and event

### 13.3 Held-since policy

Targets inherit holding period per policy:

* recommended default: preserve acquisition dates from source lots (per-lot mapping)

---

## 14. Cash Components (Optional)

### 14.1 Cash-in-lieu overlay

If any target entitlement creates fractional units:

* create `CASH_IN_LIEU` product leg + `ADJUSTMENT` cash leg
* allocate basis to fractional portion
* compute realized P&L for fractional portion (capital + FX) per existing rules

### 14.2 Cash consideration (true boot)

If event includes true cash consideration:

* model `CASH_CONSIDERATION` marker + `ADJUSTMENT` cash leg
* allocate basis to cash component
* handle realized P&L per `RFC-CA-MIXED-CONSIDERATION-01`

---

## 15. Processing Order and Dependencies

Default dependency-safe order:

1. register parent event (including `expected_target_count` where provided)
2. validate minimum child set (must identify N targets)
3. process source leg (reduce/close)
4. process target legs in deterministic order (Section 9.2)
5. finalize basis reconciliation across all targets and overlays
6. process `CASH_CONSIDERATION` marker + cash settlement (if any)
7. process `CASH_IN_LIEU` product + cash legs (if any)
8. process optional `FEE`
9. process optional `TAX`
10. mark event complete

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

### 16.1 Completion rule

Event may be `COMPLETED` only when:

* source leg completed
* all required target legs completed (N targets)
* basis reconciled within tolerance
* lot/held-since continuity outputs produced per policy
* cash overlays processed or explicitly waived by policy

---

## 17. Idempotency and Replay

### 17.1 Parent idempotency key

Example:

* `(source_system, parent_event_reference, portfolio_id)`

### 17.2 Child idempotency key

* `(parent_event_reference, child_transaction_reference)`

### 17.3 Allocation group idempotency rule

If `allocation_group_id` exists, replay must preserve the same grouping and deterministic target ordering.

Replays must not duplicate:

* any target additions
* any basis allocations
* any synthetic flows
* any cash postings

---

## 18. Validation Rules

Must validate:

* parent exists and category matches
* one source leg exists
* at least two target legs exist
* all target legs share the same `allocation_group_id` (if present)
* target legs have stable indices or deterministic ordering
* basis allocation reconciles across all targets and overlays
* dependency graph valid
* missing required target legs must park/fail based on policy

Hard-fail unless policy overrides:

* missing source leg
* fewer than two targets
* unreconcilable basis allocation mismatch
* invalid dependency graph

---

## 19. Output Contract

Expose:

* parent event (type, category, status, expected target count if known)
* source leg details (including synthetic outflow)
* all target leg details (including synthetic inflow per target)
* deterministic target ordering used
* basis allocation table (source/remaining/targets/overlays/adjustments)
* lot mapping summary
* cash overlays (cash in lieu, cash consideration) if present
* completion status

---

## 20. Worked Example: Multi-Target Demerger (2 targets)

Client holds:

* 100 shares `PARENT`
* original basis = USD 10,000

Upstream sends result:

* retain `PARENT`, remaining basis = 8,000
* receive `NEW_A`: 10 shares, basis 1,500
* receive `NEW_B`: 5 shares, basis 500

Reconcile:

* 10,000 = 8,000 + 1,500 + 500

Lotus-core:

* processes source leg once
* processes targets in deterministic order:

  * `target_leg_index = 1` → NEW_A
  * `target_leg_index = 2` → NEW_B
* emits synthetic flows for source and both targets
* marks event complete after basis reconciliation

---

## 21. Test Matrix (Minimum)

* multi-target grouping under same parent event
* deterministic ordering across targets is stable across replays
* basis reconciliation across N targets succeeds
* missing one target prevents completion
* synthetic flows created for source and each target
* source retained vs extinguished modes both covered
* cash-in-lieu overlay works in presence of multiple targets
* mixed consideration cash boot works with multiple targets (if applicable)
* idempotency prevents duplicates for target legs and cash postings

---

## 22. Configurable Policies

Must be configurable and versioned:

* expected target count strictness (`STRICT` vs `ALLOW_LATE_TARGETS`)
* deterministic ordering preference (`INDEX` vs `INSTRUMENT_ID` fallback)
* pricing source and FX source (shared/16)
* missing price/FX behavior (park vs fail)
* basis reconciliation tolerance
* lot/basis allocation policy when lot-level allocation missing
* held-since inheritance policy
* dependency enforcement strictness
* idempotency strictness
* overlay requirements (cash in lieu required? cash boot allowed?)

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 23. Final Authoritative Statement

This RFC is the canonical specification for **Multi-Target Corporate Actions** in lotus-core.

It standardizes:

* parent-child orchestration for one-source-to-many-target events
* deterministic processing order for multiple target legs
* basis allocation and reconciliation across N targets and optional cash overlays
* lot and held-since continuity requirements
* mandatory position-level synthetic flows (MVT-based) for correct position performance/contribution
* operationally safe completion semantics, idempotency, and replay safety
