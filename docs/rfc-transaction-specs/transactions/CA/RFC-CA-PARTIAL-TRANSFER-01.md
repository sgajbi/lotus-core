# RFC-CA-PARTIAL-TRANSFER-01 Canonical Partial Transfer Corporate Action Specification (Source Retained)

## 1. Document Metadata

* **Document ID:** RFC-CA-PARTIAL-TRANSFER-01
* **Title:** Canonical Partial Transfer Corporate Action Specification (Source Retained)
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                                             |
| ------- | ----- | ------ | ----------------------------------------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical partial transfer corporate action specification (source retained) |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **Partial Transfer Corporate Action** events in lotus-core, where:

* the **source instrument remains held** after the event (source retained)
* one or more **target instruments** are created or increased
* **cost basis is split/reallocated** from the source to the target(s)
* **position-level synthetic flows** (MVT-based) are recorded at product/position level for correct **position performance and contribution** analytics
* optional **cash-in-lieu** (fractional settlement) may exist and must be handled without double counting

**Important:** Synthetic flows defined here are **position-level only** and do **not** impact portfolio-level performance or portfolio cash.

---

## 3. Scope

This RFC applies to partial transfer corporate actions that upstream delivers as related child transactions, including:

* **Spin-off** (source retained, target created)
* **Demerger** (source retained, one or more targets created)
* **Split-off** (only if modeled as “source retained + partial reduction”; otherwise handled in a separate RFC)
* any of the above with **cash-in-lieu** for fractional entitlements

### 3.1 Transaction types covered by this RFC (child types)

* `SPIN_OFF` / `SPIN_IN`
* `DEMERGER_OUT` / `DEMERGER_IN`
* optional overlay: `CASH_IN_LIEU`
* cash leg for cash-in-lieu: `ADJUSTMENT` (cash instrument)
* optional: `FEE`, `TAX` (if posted as separate legs)

### 3.2 Out of scope

This RFC does not define:

* full replacement events where the source is extinguished (covered by `RFC-CA-FULL-REPLACEMENT-01`)
* entitlement calculation logic (performed upstream)
* stock splits / reverse splits
* bonus issues / stock dividends of same line
* rights subscriptions (unless later brought under CA framework)
* tax law determination (policy-driven and/or upstream-driven)

---

## 4. Referenced Shared Standards

This RFC must be read together with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/16-position-level-synthetic-flows-for-corporate-actions.md`
* `shared/07-accounting-cash-and-linkage.md` (for cash leg linkage and ADJUSTMENT rules)

---

## 5. Definitions

### 5.1 Market Value Transfer (MVT)

For a given instrument leg:

`MVT = price_at_event × quantity_at_event`

Used to create **position-level synthetic flows**.

### 5.2 Partial transfer

A corporate action where:

* the source instrument position **continues** after the event
* some economic value/cost basis is transferred to one or more target instruments

### 5.3 Basis split / reallocation

A reallocation of the existing source cost basis across:

* retained source instrument (remaining basis)
* new target instrument(s) (transferred basis)
* fractional/cash overlay (if any)

---

## 6. Core Invariants

After completion of a Partial Transfer event:

### 6.1 Source invariants (retained)

* source position remains **open**
* source quantity:

  * usually unchanged for classic spin-offs/demergers
  * may reduce for split-off-style variants (only when explicitly provided)
* source cost basis is **reduced** by the amount transferred out
* a **synthetic outflow** exists on the source product leg at MVT for the transferred economic value

### 6.2 Target invariants

* target position is created/increased per entitlement
* target cost basis is assigned per upstream basis allocation
* a **synthetic inflow** exists on the target product leg at MVT

### 6.3 Basis conservation invariant

Within tolerance:

`original_source_basis = remaining_source_basis + sum(target_basis) + fractional_basis + documented_adjustments`

### 6.4 Portfolio isolation invariant

Synthetic flows:

* must not change cash balances
* must not be treated as external portfolio funding flows
* must be consumed only by position-level performance/contribution logic

---

## 7. Parent Event Model

Every partial transfer event must be represented by a parent corporate action event.

### 7.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type`
* `processing_category = PARTIAL_TRANSFER_SOURCE_RETAINED`
* `event_status`
* `effective_date`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 7.2 Allowed corporate action types under this RFC

At minimum:

* `SPIN_OFF`
* `DEMERGER`
* `SPLIT_OFF` (only if modeled as partial transfer)
* `REORGANIZATION_PARTIAL` (if upstream uses a generic type)

---

## 8. Child Roles, Minimum Set, and Linkage

### 8.1 Canonical child roles

* `SOURCE_POSITION_REDUCE` (basis reduction and optional quantity reduction)
* `TARGET_POSITION_ADD`
* logical `COST_BASIS_REALLOCATE` (may be embedded in source/target legs)
* optional `CASH_IN_LIEU`
* optional `CHARGE` (`FEE`)
* optional `TAX`

### 8.2 Mandatory minimum child set

A valid Partial Transfer event must include:

1. one source-side partial transfer leg (`SPIN_OFF` or `DEMERGER_OUT`) representing basis transfer-out
2. one or more target-side add legs (`SPIN_IN` or `DEMERGER_IN`) representing basis transfer-in

### 8.3 Multi-target rule (demerger)

Demerger may produce multiple targets:

* the event must support **one source** and **N target** children
* each target must be independently linkable and auditable
* basis allocation must reconcile across all targets

---

## 9. Required Orchestration Fields on Each Child

Each child must support:

* `parent_event_reference`
* `child_sequence_hint` (optional but recommended)
* `dependency_reference_ids` (recommended)
* `source_instrument_id`
* `target_instrument_id`
* `source_transaction_reference`
* `target_transaction_reference`

Additionally recommended for multi-target:

* `allocation_group_id` (groups multiple target legs under same basis allocation context)
* `target_leg_index` (ordering/indexing for targets)

---

## 10. Transaction Semantics

### 10.1 Source-side partial transfer (`SPIN_OFF` / `DEMERGER_OUT`)

Booked on the **source instrument**.

Must:

* keep the position open
* reduce cost basis by the transferred-out amount
* optionally reduce quantity only when explicitly provided (split-off variants)
* emit **position-level synthetic outflow** (MVT-based) representing the economic value transferred out

### 10.2 Target-side add (`SPIN_IN` / `DEMERGER_IN`)

Booked on the **target instrument(s)**.

Must:

* add target quantity per entitlement
* assign transferred basis into the target
* emit **position-level synthetic inflow** (MVT-based)

---

## 11. Position-Level Synthetic Flow Requirements (Mandatory)

Synthetic flows are mandatory for correct position performance/contribution continuity.

### 11.1 SyntheticFlowDetails embedded model (required)

Every source and target child must carry `SyntheticFlowDetails`:

* `has_synthetic_flow: bool`
* `synthetic_flow_effective_date: date`
* `synthetic_flow_amount_local: Decimal`
* `synthetic_flow_currency: str`
* `synthetic_flow_amount_base: Decimal`
* `synthetic_flow_fx_rate_to_base: Decimal | None`
* `synthetic_flow_price_used: Decimal`
* `synthetic_flow_quantity_used: Decimal`
* `synthetic_flow_valuation_method: SyntheticFlowValuationMethod`
* `synthetic_flow_classification: SyntheticFlowClassification`
* `synthetic_flow_price_source: SyntheticFlowPriceSource`
* `synthetic_flow_fx_source: SyntheticFlowFxSource`

### 11.2 SyntheticFlowClassification (required)

* `POSITION_TRANSFER_OUT`
* `POSITION_TRANSFER_IN`
* `POSITION_CASH_IN_LIEU_OUT` (only for cash-in-lieu product leg when applicable)

### 11.3 Source synthetic outflow (required)

For `SPIN_OFF` / `DEMERGER_OUT`:

* `synthetic_flow_classification = POSITION_TRANSFER_OUT`
* `synthetic_flow_amount_local = - (price_source × qty_reference)`
* effective date = parent effective date
* valuation method = `MVT_PRICE_X_QTY`

#### 11.3.1 Quantity used for source MVT (policy-driven)

Because the source is retained, the “quantity reference” must be explicit:

* default: use **source quantity held** at event effective date
* alternative: use **economic portion transferred** if upstream provides a specific transfer quantity equivalent

This must be configurable via:

* `source_mvt_quantity_mode = FULL_HELD_QUANTITY | TRANSFER_EQUIVALENT_QUANTITY`

Recommended default for classic spin-off: `FULL_HELD_QUANTITY` (because the outflow represents the economic transfer from the parent line as a whole).

### 11.4 Target synthetic inflow (required)

For each `SPIN_IN` / `DEMERGER_IN` target:

* `synthetic_flow_classification = POSITION_TRANSFER_IN`
* `synthetic_flow_amount_local = + (price_target × qty_received)`
* effective date = parent effective date
* valuation method = `MVT_PRICE_X_QTY`

### 11.5 Pricing requirements (deterministic)

Synthetic flows require prices:

* prefer upstream-provided prices per leg
* if not provided, lotus-core may fetch market prices only if configured
* missing prices must park/fail per policy:

  * recommended: `PARK_MISSING_PRICE`

### 11.6 FX requirements (base currency)

If base reporting is required:

* `amount_base = amount_local × fx_rate_to_base`
* FX must be upstream-provided or derived from FX service per policy
* missing FX parks/fails per policy

### 11.7 Portfolio isolation rule (mandatory)

Synthetic flows:

* must not create any cash legs
* must not affect cash balances
* must not be treated as deposit/withdrawal or external funding flow
* must be consumed only by position-level performance/contribution logic

---

## 12. Cost Basis Split Rules (Core of Partial Transfer)

### 12.1 Inputs

Lotus-core expects upstream to provide, for each event:

* original source basis (or it can be derived from lot state)
* remaining source basis after event (or basis transferred out)
* target basis amounts per target leg
* basis allocation rules metadata (optional but recommended)

Lotus-core does not calculate entitlement, but must validate basis allocation consistency.

### 12.2 Basis transfer-out rule

The source-side child must indicate:

* `basis_transferred_out` (local/base)

Then:

* `remaining_source_basis = original_source_basis - basis_transferred_out`

### 12.3 Basis transfer-in rule

Each target-side child must indicate:

* `basis_transferred_in` (local/base)

### 12.4 Basis conservation rule (mandatory)

Within tolerance:

`original_source_basis = remaining_source_basis + Σ(basis_transferred_in_targets) + fractional_basis + adjustments`

### 12.5 Lot-level basis allocation (recommended)

If upstream provides lot-level allocation, lotus-core must preserve it.

If upstream provides only aggregate basis, lotus-core must support a policy to allocate basis across lots for target positions:

* `ALLOCATE_PRO_RATA_BY_SOURCE_LOT_COST` (recommended default)
* `ALLOCATE_OLDEST_LOTS_FIRST`
* `ALLOCATE_NEW_SINGLE_LOT`

These are internal bookkeeping policies; upstream remains the source of truth for totals.

---

## 13. Lot and Held-Since Continuity (Mandatory)

### 13.1 Source lots

Because the source remains open:

* source lots remain, but their cost basis is reduced per allocation policy
* lot linkage must remain auditable

### 13.2 Target lots

Targets must have:

* lot creation with linkage back to source event and (if possible) source lots
* held-since inheritance per policy

### 13.3 Held-since rule (recommended default)

Targets inherit holding period from source lots (per-lot mapping if available). If not available, preserve earliest acquisition date.

---

## 14. Cash-in-Lieu Overlay (Fractional Settlement)

### 14.1 When it applies

If target entitlements create fractional units that cannot be delivered:

* create `CASH_IN_LIEU` as an overlay child

### 14.2 Required legs

Cash-in-lieu must include:

1. **product leg** (fractional entitlement disposal, basis allocation, realized P&L)
2. **cash leg** `ADJUSTMENT` (cash settlement)

### 14.3 Product leg requirements

* fractional quantity (by target instrument)
* fractional MVT = `price_target × fractional_qty`
* allocated basis to fractional portion
* realized P&L breakdown:

  * `realized_capital_pnl`
  * `realized_fx_pnl`
  * `realized_total_pnl`

### 14.4 Cash leg requirements (`ADJUSTMENT`)

* actual cash posted to cash account
* linked to product leg via:

  * same `economic_event_id`
  * same `linked_transaction_group_id`
  * `linked_cash_transaction_id`

### 14.5 No double counting rule (position analytics)

* position analytics must treat product leg as the event economics
* cash leg updates cash only and must not be treated as position flow

---

## 15. Processing Order and State Machine

### 15.1 Default processing order (dependency-safe)

1. register parent event
2. validate minimum child set (including N targets for demerger)
3. process source leg (`SPIN_OFF` / `DEMERGER_OUT`)
4. process all target legs (`SPIN_IN` / `DEMERGER_IN`) in deterministic order
5. finalize basis reconciliation (including all targets)
6. process optional `CASH_IN_LIEU` product leg(s)
7. process `ADJUSTMENT` cash leg(s)
8. process optional `FEE`
9. process optional `TAX`
10. mark event complete

### 15.2 Event states (required)

* `PENDING_CHILDREN`
* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `PARKED`
* `FAILED`
* `COMPLETED`

### 15.3 Completion rule

Event may be `COMPLETED` only when:

* source leg succeeded
* all required target legs succeeded
* basis reconciliation succeeded within tolerance
* lot/held-since continuity output produced per policy
* overlays are processed or explicitly waived by policy

---

## 16. Idempotency and Replay

### 16.1 Parent idempotency key (required)

Example:

* `(source_system, parent_event_reference, portfolio_id)`

### 16.2 Child idempotency key (required)

* `(parent_event_reference, child_transaction_reference)`

### 16.3 Replay rule

Replays must not duplicate:

* basis reduction on source
* target creation
* synthetic flows
* cash-in-lieu cash settlements
* fees/taxes

---

## 17. Validation Rules

The engine must validate at minimum:

* parent exists and category matches
* required source child exists
* required target child(ren) exist
* source/target instrument ids populated
* dependency graph valid
* target legs cannot finalize before source leg where required
* basis transfer-out and transfer-in totals reconcile within tolerance
* synthetic flow inputs (price/qty) are present or synthetic flows are upstream-provided
* lot continuity rules can be satisfied

### 17.1 Hard-fail conditions (unless policy override)

* missing parent
* missing source leg
* missing required target legs
* invalid dependency references
* unreconcilable basis mismatch
* missing price/FX where policy requires hard fail

---

## 18. Output Contract

Expose:

* parent event view (type, category, status)
* source leg view (including synthetic outflow)
* target leg views (including synthetic inflows)
* basis reconciliation summary
* lot mapping and held-since outputs per policy
* cash-in-lieu product + cash legs (if present)
* completion status

---

## 19. Worked Example A: Spin-off (single target)

Client holds:

* 100 shares of `PARENT`
* original basis = USD 10,000

Upstream sends:

* entitlement: 10 shares of `NEWCO`
* basis allocation:

  * remaining basis on `PARENT` = 8,000
  * basis on `NEWCO` = 2,000
* prices at event:

  * `PARENT` price = 80
  * `NEWCO` price = 20

### Source child — `SPIN_OFF`

* reduces source basis by 2,000 (remaining 8,000)
* synthetic outflow at source:

  * mode default `FULL_HELD_QUANTITY`
  * `synthetic_outflow = - (80 × 100) = -8,000`

### Target child — `SPIN_IN`

* adds 10 `NEWCO`
* assigns basis 2,000
* synthetic inflow:

  * `synthetic_inflow = + (20 × 10) = +200`

Result:

* parent remains open with reduced basis
* child starts with synthetic inflow base for its own performance series

---

## 20. Worked Example B: Demerger (multi-target)

Client holds:

* 100 shares of `PARENT`
* original basis = USD 10,000

Upstream sends:

* target A: 10 shares, basis 1,500
* target B: 5 shares, basis 500
* remaining parent basis = 8,000

Lotus-core must:

* process source leg once
* process both targets
* reconcile basis:

  * 10,000 = 8,000 + 1,500 + 500

---

## 21. Test Matrix (Minimum)

### 21.1 Orchestration tests

* parent before children finalize
* source before target(s)
* deterministic ordering for multi-target
* event not complete while targets pending

### 21.2 Synthetic flow tests

* source synthetic outflow generated per configured quantity mode
* target synthetic inflow generated per target entitlement
* synthetic flows do not affect cash balances
* synthetic flows excluded from portfolio-level funding flows

### 21.3 Basis tests

* basis reduction on source correct
* basis assigned to targets correct
* basis conserved within tolerance
* lot allocation policy applied and auditable

### 21.4 Lot/held-since tests

* source lots updated per policy
* target lots linked per policy
* held-since preserved per policy

### 21.5 Cash-in-lieu tests

* product + ADJUSTMENT cash legs created
* fractional basis allocation correct
* realized pnl computed correctly
* no double counting between product and cash legs

### 21.6 Replay tests

* replay does not double apply basis reductions or target creations
* replay does not duplicate synthetic flows or cash postings

---

## 22. Configurable Policies

Must be configurable and versioned:

* pricing source (upstream vs market data)
* FX source
* missing price/FX behavior (park vs fail)
* source MVT quantity mode for partial transfer (`FULL_HELD_QUANTITY` vs `TRANSFER_EQUIVALENT_QUANTITY`)
* basis reconciliation tolerance
* lot/basis allocation policy
* held-since inheritance policy
* dependency enforcement strictness
* idempotency strictness
* cash-in-lieu basis allocation method (if not supplied upstream)

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 23. Final Authoritative Statement

This RFC defines the canonical specification for **Partial Transfer Corporate Actions (Source Retained)** in lotus-core.

It standardizes:

* parent-child orchestration for partial transfer events
* `SPIN_OFF` / `SPIN_IN` and `DEMERGER_OUT` / `DEMERGER_IN` semantics
* mandatory position-level synthetic flows at MVT for correct position performance/contribution
* basis split and conservation rules across source and targets
* lot and held-since continuity requirements
* correct cash-in-lieu handling with product leg + `ADJUSTMENT` cash leg and no double counting
* deterministic ordering, idempotency, replay safety, and operationally safe event states
