# RFC-CA-REVERSAL-01 Canonical Corporate Action Reversal, Correction, and Rebook Specification

## 1. Document Metadata

* **Document ID:** RFC-CA-REVERSAL-01
* **Title:** Canonical Corporate Action Reversal, Correction, and Rebook Specification
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
| 1.0.0   | *TBD* | *TBD*  | Initial canonical CA reversal/correction/rebook specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for handling **Corporate Action lifecycle reversals** in lotus-core, including:

* **CANCEL** (full reversal of a previously processed corporate action event)
* **CORRECTION** (a corrected restatement of a previously processed event)
* **REBOOK** (cancel the old event and apply a new event with updated terms)

This RFC is cross-cutting: it applies to **all corporate action categories** already defined:

* `RFC-CA-FULL-REPLACEMENT-01`
* `RFC-CA-PARTIAL-TRANSFER-01`
* `RFC-CA-MIXED-CONSIDERATION-01`
* `RFC-CA-MULTI-TARGET-01`

The goal is to guarantee correctness and operational safety across:

* positions
* lots and held-since
* cost basis
* cash legs and settlement
* position-level synthetic flows used for position performance/contribution
* time series and history restatement
* idempotency and replay

---

## 3. Scope

This RFC covers:

* canonical event lifecycle statuses and state machine
* linkage model from reversal/correction events to original events
* ordering and dependency rules for reversing child transactions
* correctness and reconciliation constraints after reversal
* replay/idempotency for reversal flows
* query/read-model visibility rules for corrected history

### 3.1 Out of scope

This RFC does not define:

* entitlement calculation logic (upstream responsibility)
* broker/custodian message formats
* general non-CA transaction cancellation rules (covered elsewhere)

---

## 4. Referenced Standards

This RFC must be read together with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/16-position-level-synthetic-flows-for-corporate-actions.md`
* `shared/07-accounting-cash-and-linkage.md`
* all CA category RFCs listed in Section 2

---

## 5. Key Definitions

### 5.1 Original Event

The corporate action event that was previously processed and is now subject to cancel/correct/rebook.

### 5.2 Reversal Event

A corporate action event that explicitly reverses a previously processed event.

### 5.3 Correction

A new event that supersedes the original event by changing one or more values (quantities, basis allocations, cash components, dates, etc.).

Canonical handling is: **CANCEL + REBOOK** (unless the upstream provides an explicit delta-only model and the bank policy allows it).

### 5.4 Rebook

A new replacement event applied after canceling the original event. The rebook is the new canonical truth.

### 5.5 Restatement

A time-series correction that changes historical states because the corrected event effective date may be in the past.

---

## 6. Core Principles

### 6.1 Deterministic reversal

Reversal must be deterministic, auditable, and replay-safe.

### 6.2 Full traceability

Every reversal/correction must be linkable to the original event with immutable identifiers.

### 6.3 Preserve historical audit

Original events must not be deleted. They must be marked as superseded/canceled and remain queryable for audit with clear status.

### 6.4 State safety

The platform must prevent a partially reversed event from being represented as fully corrected.

### 6.5 Position-level synthetic flow safety

Synthetic flows are position-level only, but they still must be reversed/restated correctly for position performance and contribution.

---

## 7. Canonical Event Lifecycle Types and Statuses

### 7.1 Lifecycle operation enum

`CorporateActionLifecycleOperation`:

* `ORIGINAL`
* `CANCEL`
* `CORRECT`
* `REBOOK`

### 7.2 Event status enum (minimum)

`CorporateActionEventStatus`:

* `PENDING_CHILDREN`
* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `PARKED`
* `FAILED`
* `COMPLETED`
* `CANCELED` (original event is fully reversed)
* `SUPERSEDED` (original event replaced by corrected/rebooked event)

### 7.3 Child status enum (minimum)

`CorporateActionChildStatus`:

* `READY`
* `APPLIED`
* `REVERSED`
* `FAILED`
* `PARKED`

---

## 8. Linkage Model (Mandatory)

### 8.1 Required linkage fields on reversal/correction events

Every CANCEL/CORRECT/REBOOK event must include:

* `related_original_event_id` (the original `corporate_action_event_id`)
* `related_original_parent_event_reference`
* `correction_reason_code` (optional but recommended)
* `correction_reference` (optional but recommended, upstream id)

### 8.2 Required linkage on each child transaction

Every reversal/correction child must include:

* `related_original_child_transaction_reference`
* `related_original_child_transaction_id` (if known)
* `parent_event_reference` of the reversal/correction event

### 8.3 Linking cash legs

For any cash settlement leg (`ADJUSTMENT`) linked to a CA overlay:

* the reversal must reference the original cash leg via:

  * `related_original_cash_transaction_id` (recommended)
  * and shared economic event linkage

---

## 9. Canonical Handling Model

### 9.1 CANCEL handling model

A CANCEL event must reverse all applied effects of the original event.

The reversal must:

* reverse source/target quantity effects
* reverse lot creation/mapping
* reverse basis allocations
* reverse cash overlays (cash consideration and cash-in-lieu)
* reverse fee/tax legs
* reverse synthetic flows (position-level)

After cancellation:

* portfolio state must match exactly what it would have been if the original event never occurred (within defined rounding tolerance policies)

### 9.2 CORRECT handling model

Canonical approach:

* CORRECT = CANCEL original + REBOOK new

Meaning:

1. apply a CANCEL event linked to the original event
2. apply a new REBOOK event containing the corrected child set

This model is mandatory unless a customer explicitly configures and approves delta-only correction.

### 9.3 REBOOK handling model

A REBOOK event is processed as a new original event, but must be linked to the original event as a correction chain.

The rebook event must:

* carry its own parent event identifiers
* contain full child set required for its category
* produce its own reconciliation results
* mark original event as `SUPERSEDED` and itself as `COMPLETED`

---

## 10. Reversal of Child Transactions (Rules)

### 10.1 Reverse in strict safe order (reverse dependencies)

Reversal must reverse child effects in reverse order of original application, at minimum:

1. reverse charges/taxes (`FEE`, `TAX`)
2. reverse cash overlays:

   * reverse `ADJUSTMENT` cash legs first (cash settlement)
   * reverse cash overlay product legs (`CASH_IN_LIEU`, `CASH_CONSIDERATION`)
3. reverse target legs (`*_IN`) (remove created/increased target holdings and their lots)
4. reverse basis reallocation effects
5. reverse source leg (`*_OUT` or `SPIN_OFF/DEMERGER_OUT` basis reduction)
6. finalize parent event cancellation

This ordering prevents orphaned lots, negative positions, and cash mismatches.

### 10.2 Reversal sign rules

A reversal child must carry explicit reversal semantics. Recommended approach:

* introduce `is_reversal: bool`
* and/or `reversal_of_transaction_id`
* and store `reversal_reason`

Reversal effects are:

* quantity deltas are negated
* basis deltas are negated
* cash deltas are negated (for cash legs)
* synthetic flows are negated (position-level)

### 10.3 Partial application handling

If original event is `PARTIALLY_APPLIED`, the CANCEL must:

* reverse only successfully applied children
* mark cancellation as incomplete until remaining applied items are reversed or explicitly waived by policy
* never mark `CANCELED` until all applied effects are reversed

---

## 11. Position-Level Synthetic Flow Reversal

Synthetic flows created under `shared/16` must be reversed as part of cancellation/correction.

### 11.1 Rule

For any child transaction with `SyntheticFlowDetails`:

* reversal must create an equal and opposite synthetic flow with same effective date unless policy specifies restated-date handling
* synthetic flows remain position-level only and do not touch cash balances

### 11.2 Cash-in-lieu synthetic handling

If cash-in-lieu product legs include synthetic flow classifications, reversal must negate them as well.

---

## 12. Cost Basis and Lot Reversal

### 12.1 Basis reversal rule

The basis allocation applied by the original event must be reversed so that:

* source and target bases return to their pre-event values
* any fractional basis allocations return
* basis conservation holds after reversal

### 12.2 Lot reversal rule

Lots created due to corporate action target legs must be removed/reversed.

Lot mapping artifacts must be preserved for audit but must not remain active in the post-cancel state.

### 12.3 Held-since reversal rule

Held-since and acquisition-date continuity changes must be reversed consistent with lot reversal.

---

## 13. Cash Legs Reversal

### 13.1 Cash settlement reversal

Any cash settlement legs (`ADJUSTMENT`) created/provided for CA overlays must be reversed:

* inflow becomes outflow of same amount and currency
* outflow becomes inflow of same amount and currency

### 13.2 Settlement-date policy

If cash settlement has already occurred historically, reversal must still post the reversing cash transaction as provided by upstream (or generated by policy if permitted). Lotus-core must not invent settlement dates beyond policy.

### 13.3 No double counting

Reversal must reverse both:

* product overlay leg economics (basis/pnl)
* and the cash settlement leg

so that both position analytics and cash balances return to pre-event state.

---

## 14. Time Series Restatement Rules

Corporate action corrections often occur after the effective date. Lotus-core must support restatement.

### 14.1 Restatement modes (policy-driven)

`TimeSeriesRestatementMode`:

* `RESTATEMENT_REQUIRED` (default for private banking reporting)
* `RESTATEMENT_FROM_BOOKING_DATE` (rare)
* `NO_RESTATEMENT_APPEND_ONLY` (only for non-regulatory, non-audited use cases)

### 14.2 Rule

If the original effective date is in the past, cancellation/rebook must trigger a restatement from:

* the earliest affected effective date across original and rebook events

Time series engines must recompute derived series as required by platform design.

---

## 15. Processing Order for Correction (CANCEL + REBOOK)

Canonical order:

1. validate correction/reversal linkage to original event
2. apply CANCEL for original event (dependency-safe reverse order)
3. mark original event as `CANCELED` (if pure cancel) or `SUPERSEDED` (if correction)
4. apply REBOOK event as a new corporate action event using the correct CA category RFC
5. reconcile and mark REBOOK event `COMPLETED`

---

## 16. Idempotency and Replay

### 16.1 Parent idempotency key (reversal)

For CANCEL/CORRECT/REBOOK events:

* `(source_system, parent_event_reference, lifecycle_operation, related_original_parent_event_reference, portfolio_id)`

### 16.2 Child idempotency key (reversal)

* `(parent_event_reference, child_transaction_reference)`

### 16.3 Replay rule

Replays must not:

* reverse twice
* apply corrected event twice
* duplicate cash reversals
* duplicate synthetic flow reversals

---

## 17. Validation Rules

Must validate:

* original event exists
* original event status is eligible for cancel/correct per policy
* linkage fields are present
* every reversal child references an original child
* reverse order dependencies are satisfiable
* basis and quantity states will not become invalid mid-reversal (or else the event must park)

Hard-fail unless policy override:

* missing original event reference
* missing child linkage references
* mismatch between reversal children and original children beyond policy tolerance
* attempt to cancel an event that was never applied (unless policy allows noop cancel)

---

## 18. Output Contract

Expose:

* original event record with updated status (`CANCELED` or `SUPERSEDED`)
* reversal event record (CANCEL/CORRECT/REBOOK) with status
* child-level reversal mapping:

  * original child reference → reversal child reference
* basis reconciliation before/after
* cash reconciliation before/after
* synthetic flow reconciliation before/after
* time-series restatement markers (if applicable)

---

## 19. Worked Example (High Level)

Original event:

* `MERGER_OUT`, `MERGER_IN`, `CASH_IN_LIEU`, `ADJUSTMENT`

Correction arrives changing:

* target quantity
* cash-in-lieu proceeds
* basis allocations

Canonical handling:

1. CANCEL original:

   * reverse `ADJUSTMENT`
   * reverse `CASH_IN_LIEU` product leg
   * reverse `MERGER_IN`
   * reverse `MERGER_OUT`
   * reverse synthetic flows for source/target legs
2. REBOOK new corrected event:

   * apply new `MERGER_OUT`, `MERGER_IN`, `CASH_IN_LIEU`, `ADJUSTMENT`
   * generate new synthetic flows at MVT
3. mark original `SUPERSEDED`, new event `COMPLETED`

---

## 20. Test Matrix (Minimum)

### 20.1 Cancel tests (per CA category)

* cancel full replacement event returns portfolio to exact pre-event state
* cancel partial transfer returns basis split back correctly and source retained state restored
* cancel mixed consideration reverses cash consideration cash legs and pnl effects
* cancel multi-target reverses all targets deterministically

### 20.2 Correction tests

* correction = cancel + rebook produces final state identical to “only corrected event applied”
* correction restates time series appropriately

### 20.3 Idempotency tests

* replay cancel does not double reverse
* replay rebook does not double apply
* replay cash reversal does not duplicate cash

### 20.4 Partial application tests

* cancel partially applied event reverses only applied legs and remains incomplete until resolved

### 20.5 Reconciliation tests

* quantity, basis, cash, synthetic flows reconcile pre/post reversal
* no negative positions created mid-reversal beyond policy allowances

---

## 21. Configurable Policies

Must be configurable and versioned:

* eligibility rules for cancel/correct (allowed statuses)
* correction handling model (`CANCEL_PLUS_REBOOK` default, `DELTA_ONLY` optional)
* time series restatement mode
* rounding and tolerance for reconciliation
* strictness of child matching (must match exact set vs allow subset)
* whether lotus-core may generate reversal legs if upstream omits them (recommended default: upstream provides)

All reversal/correction events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 22. Final Authoritative Statement

This RFC defines the canonical specification for **Corporate Action Reversal, Correction, and Rebook** handling in lotus-core.

It standardizes:

* explicit linkage of reversal events to original events
* deterministic reversal ordering across child legs
* reversal of positions, lots, basis, cash legs, and synthetic flows
* correction handling as **CANCEL + REBOOK** by default
* replay safety and idempotency
* operationally safe statuses and time-series restatement behavior

If any implementation or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
