# RFC-CA-FULL-REPLACEMENT-01 Canonical Full Replacement Corporate Action Transfer Specification

## 1. Document Metadata

* **Document ID:** RFC-CA-FULL-REPLACEMENT-01
* **Title:** Canonical Full Replacement Corporate Action Transfer Specification
* **Version:** 1.2.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                                                                        |
| ------- | ----- | ------ | -------------------------------------------------------------------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical full replacement corporate action transfer specification                                     |
| 1.1.0   | *TBD* | *TBD*  | Added position-level synthetic flow requirements and clarified cash-in-lieu handling                           |
| 1.2.0   | *TBD* | *TBD*  | Clarified pricing/FX sourcing, lot continuity, idempotency, state machine, reconciliation, and worked examples |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **Full Replacement Corporate Action Transfer** events in lotus-core.

This category covers corporate actions where:

* a **source instrument** holding is **fully extinguished / fully replaced**
* one or more **target instruments** are created or increased
* **cost basis** is transferred out of the source and assigned into the target(s)
* **position-level synthetic flows** are recorded at **Market Value Transfer (MVT = price × quantity)** on the product leg for correct **position performance and contribution** analytics
* optional **cash-in-lieu** (fractional settlement) may exist and must be processed without double counting

**Important:** The synthetic flows defined in this RFC are **position-level only** and **do not impact portfolio-level performance or portfolio cash**.

---

## 3. Scope

This RFC applies to the following high-priority bundled corporate action patterns:

* stock-for-stock mergers that fully replace the source line
* mandatory share exchanges
* security replacements / line migrations that extinguish the old line
* schemes of arrangement that fully replace the source line
* identifier replacement that results in the old line being retired (economic replacement)
* any of the above with fractional **cash-in-lieu**

### 3.1 Transaction types covered by this RFC (child types)

* `MERGER_OUT` / `MERGER_IN`
* `EXCHANGE_OUT` / `EXCHANGE_IN`
* `REPLACEMENT_OUT` / `REPLACEMENT_IN`
* overlay: `CASH_IN_LIEU`
* cash leg for cash-in-lieu: `ADJUSTMENT` (cash instrument)

### 3.2 Out of scope

This RFC does not define:

* spin-offs / demergers where the source remains open (handled by Partial Transfer RFC)
* partial exchanges unless explicitly modeled as a separate category
* stock splits / reverse splits
* bonus issues / stock dividends of the same line
* entitlement calculation logic (performed upstream)
* tax law determination (policy-driven, upstream-driven)

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

MVT is used to create **position-level synthetic flows**.

### 5.2 Full Replacement

A corporate action where the source instrument position is fully closed/extinguished and replaced by one or more target instrument positions.

### 5.3 Position-level synthetic flow

A non-cash, product-leg flow recorded only for position performance/contribution continuity.

* no cash account impact
* no ledger debit/credit
* not an external portfolio flow

---

## 6. Core Invariants

After completion of a Full Replacement event:

### 6.1 Source invariants

* source position quantity for the replaced line = `0`
* source cost basis for the replaced line = `0` (unless an explicit residual policy allows otherwise)
* a **synthetic outflow** exists at the source product leg at MVT on event effective date

### 6.2 Target invariants

* target position quantity equals entitlement delivered (whole-share quantity)
* target cost basis equals the transferred basis allocated to the target
* a **synthetic inflow** exists at the target product leg at MVT on event effective date

### 6.3 Portfolio isolation invariant

Synthetic flows:

* must not change cash balances
* must not be treated as portfolio funding flows
* must be consumed only by position-level performance and contribution calculations

---

## 7. Parent Event Model

Every full replacement event must be represented by a parent corporate action event.

### 7.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type`
* `processing_category = FULL_REPLACEMENT_TRANSFER`
* `event_status`
* `effective_date`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 7.2 Allowed corporate action types under this RFC

At minimum:

* `MERGER`
* `MANDATORY_EXCHANGE`
* `SECURITY_REPLACEMENT`
* `SCHEME_OF_ARRANGEMENT`
* `IDENTIFIER_REPLACEMENT`

---

## 8. Child Roles, Minimum Set, and Linkage

### 8.1 Canonical child roles

* `SOURCE_POSITION_CLOSE`
* `TARGET_POSITION_ADD`
* logical `COST_BASIS_REALLOCATE` (may be embedded in source/target legs)
* optional `CASH_IN_LIEU`
* optional `CHARGE` (`FEE`)
* optional `TAX`

### 8.2 Mandatory minimum child set

A valid Full Replacement event must include:

1. exactly one source-side close leg (`*_OUT`) per replaced source economic line
2. exactly one target-side add leg (`*_IN`) per replacement target economic line

### 8.3 Required orchestration/linkage fields on each child

Each child must support:

* `parent_event_reference`
* `child_sequence_hint` (optional but recommended)
* `dependency_reference_ids` (recommended)
* `source_instrument_id`
* `target_instrument_id`
* `source_transaction_reference`
* `target_transaction_reference`

---

## 9. Transaction Semantics

### 9.1 Source-side child (`*_OUT`)

Transaction types:

* `MERGER_OUT`
* `EXCHANGE_OUT`
* `REPLACEMENT_OUT`

Booked on the **source instrument**.

Must:

* remove source quantity (close the position)
* transfer out cost basis (source basis becomes zero unless residual policy applies)
* emit **position-level synthetic outflow** (MVT-based) per Section 10

### 9.2 Target-side child (`*_IN`)

Transaction types:

* `MERGER_IN`
* `EXCHANGE_IN`
* `REPLACEMENT_IN`

Booked on the **target instrument**.

Must:

* add target quantity
* receive/assign cost basis transferred from source
* emit **position-level synthetic inflow** (MVT-based) per Section 10

---

## 10. Position-Level Synthetic Flow Requirements (Mandatory)

Synthetic flows are mandatory for correct **position performance and contribution** continuity.

### 10.1 SyntheticFlowDetails embedded model (required)

Every `*_OUT` and `*_IN` child must carry `SyntheticFlowDetails`:

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

### 10.2 Enums (required)

* `SyntheticFlowValuationMethod`:

  * `MVT_PRICE_X_QTY`

* `SyntheticFlowClassification`:

  * `POSITION_TRANSFER_OUT`
  * `POSITION_TRANSFER_IN`
  * `POSITION_CASH_IN_LIEU_OUT` (used only for cash-in-lieu product leg when applicable)

* `SyntheticFlowPriceSource`:

  * `UPSTREAM`
  * `MARKET_DATA`
  * `MANUAL_OVERRIDE`

* `SyntheticFlowFxSource`:

  * `UPSTREAM`
  * `FX_SERVICE`
  * `MANUAL_OVERRIDE`

### 10.3 Source synthetic outflow (required)

For `*_OUT`:

* `synthetic_flow_classification = POSITION_TRANSFER_OUT`
* `synthetic_flow_amount_local = - (price_source × qty_removed)`
* `synthetic_flow_price_used = price_source`
* `synthetic_flow_quantity_used = qty_removed`
* `synthetic_flow_effective_date = parent.effective_date`
* `synthetic_flow_valuation_method = MVT_PRICE_X_QTY`

### 10.4 Target synthetic inflow (required)

For `*_IN`:

* `synthetic_flow_classification = POSITION_TRANSFER_IN`
* `synthetic_flow_amount_local = + (price_target × qty_received)`
* `synthetic_flow_price_used = price_target`
* `synthetic_flow_quantity_used = qty_received`
* `synthetic_flow_effective_date = parent.effective_date`
* `synthetic_flow_valuation_method = MVT_PRICE_X_QTY`

### 10.5 Pricing requirements (deterministic)

Synthetic flows require a price for each leg:

* Prefer **upstream-provided** price per leg
* If not provided, lotus-core may fetch market price only if configured
* If neither is available, behavior must be policy-driven:

  * recommended default: `PARK_MISSING_PRICE`
  * alternative: `HARD_FAIL_MISSING_PRICE`

### 10.6 FX requirements (base currency)

If base currency reporting is required and differs from the synthetic flow currency:

* `synthetic_flow_amount_base = synthetic_flow_amount_local × fx_rate_to_base`
* FX must be upstream-provided or derived from configured FX service
* Missing FX must park/fail based on policy

### 10.7 Portfolio isolation rule (mandatory)

Synthetic flows:

* must not create any cash legs
* must not affect cash balances
* must not be treated as deposit/withdrawal or external portfolio flow
* must only be used by position-level performance/contribution calculations

---

## 11. Cost Basis Rules

### 11.1 Full basis transfer rule

For standard full replacement events:

* all transferable source basis must move out of the source line
* that basis must be assigned into the target line(s) and/or fractional overlay (cash-in-lieu basis allocation)

### 11.2 Basis conservation rule

Within tolerance, the system must reconcile:

`basis_out_of_source = basis_into_target + basis_allocated_to_fractional + documented_adjustments`

### 11.3 Residual basis policy

If an institution allows residual basis on source (rare), this must be explicit and configurable:

* `allow_residual_source_basis: bool`
* `residual_basis_reason: enum` (if enabled)

Default: not allowed.

---

## 12. Lot and Held-Since Continuity (Mandatory)

Full replacement events must define how lot lineage and holding period continuity is preserved.

### 12.1 Lot continuity policy (configurable)

* `PRESERVE_LOT_DATES` (recommended default)
* `RESET_HELD_SINCE_TO_EVENT_DATE` (exception)
* `PRESERVE_SOURCE_LOT_IDS` (optional, when feasible)
* `CREATE_NEW_LOTS_WITH_LINKAGE` (recommended when ids cannot be preserved)

### 12.2 Required lot linkage outputs

For each event, the system must be able to produce:

* `source_lot_ids`
* `target_lot_ids`
* `lot_mapping_reference_id` or explicit mapping list

### 12.3 Held-since rule (recommended default)

* target held-since is inherited from source lot acquisition dates (per-lot mapping)
* at minimum, the earliest acquisition date should be preserved where per-lot mapping is unavailable

---

## 13. Cash-in-Lieu Overlay (Fractional Settlement)

Cash-in-lieu introduces **real cash settlement** plus fractional entitlement disposal.

### 13.1 Cash-in-lieu child

* `transaction_type = CASH_IN_LIEU`
* `child_role = CASH_IN_LIEU`

### 13.2 Required legs

Cash-in-lieu must have:

1. **product leg** (fractional entitlement disposal, basis allocation, realized P&L)
2. **cash leg** (actual cash settlement)

### 13.3 Cash leg transaction type

The cash settlement must be represented as:

* `transaction_type = ADJUSTMENT` (cash instrument)

The cash leg must be linked to the `CASH_IN_LIEU` product leg using:

* shared `economic_event_id`
* shared `linked_transaction_group_id`
* and a direct linkage field:

  * `linked_cash_transaction_id` (recommended)

### 13.4 Product leg requirements

Cash-in-lieu product leg must include:

* `fractional_quantity`
* `fractional_mvt = price_target × fractional_quantity`
* `allocated_cost_basis_fractional`
* realized P&L breakdown:

  * `realized_capital_pnl`
  * `realized_fx_pnl`
  * `realized_total_pnl`

Optional but recommended:

* `synthetic_flow_classification = POSITION_CASH_IN_LIEU_OUT`

### 13.5 No double counting rule (position analytics)

* position-level engines must use the **product leg** for cash-in-lieu economics (basis + realized pnl)
* the `ADJUSTMENT` cash leg must be treated as **cash-balance-only** and excluded from position-level contribution flows

---

## 14. Processing Order and State Machine

### 14.1 Default processing order (dependency-safe)

1. register parent event
2. validate minimum required child set
3. process source `*_OUT`
4. process target `*_IN`
5. reconcile basis + lot continuity outputs
6. process `CASH_IN_LIEU` product leg (if any)
7. process `ADJUSTMENT` cash leg (if any)
8. process optional `FEE`
9. process optional `TAX`
10. mark parent event complete

Arrival order must not be assumed.

### 14.2 Event states (required)

* `PENDING_CHILDREN`
* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `PARKED`
* `FAILED`
* `COMPLETED`

### 14.3 Completion rule

Event status may be `COMPLETED` only when:

* required `*_OUT` succeeded
* required `*_IN` succeeded
* basis reconciliation succeeded
* lot continuity output produced per policy
* optional overlays (cash-in-lieu, fee, tax) are either completed or explicitly waived by policy

---

## 15. Idempotency and Replay

### 15.1 Parent idempotency key (required)

A stable unique key must be enforced, for example:

* `(source_system, parent_event_reference, portfolio_id)`

### 15.2 Child idempotency key (required)

* `(parent_event_reference, child_transaction_reference)`

### 15.3 Cash leg idempotency key (required)

* `(parent_event_reference, cash_leg_reference)` or deterministic linkage to cash-in-lieu product leg id

### 15.4 Replay rule

Replays must not duplicate:

* source closure
* target creation
* basis transfer
* synthetic flows
* cash-in-lieu cash settlement
* fees/taxes

---

## 16. Validation Rules

The engine must validate at minimum:

* parent event exists and category matches
* children belong to the parent via `parent_event_reference`
* required `*_OUT` child exists
* required `*_IN` child exists
* source/target instrument ids populated
* dependency graph is valid
* target child cannot finalize before required source child
* sufficient source quantity exists
* basis transfer is present or derivable per policy
* basis conservation holds within configured tolerance
* synthetic flow inputs (price/qty) are present, or synthetic flows are upstream-provided

### 16.1 Hard-fail conditions (unless policy override)

* missing parent event
* missing required source child
* missing required target child
* invalid dependency graph
* insufficient source quantity
* unreconcilable basis mismatch
* missing price/FX when policy requires hard fail

---

## 17. Output Contract

After successful processing, the platform must expose:

* parent corporate action event view (with status and category)
* source child view (`*_OUT`)
* target child view (`*_IN`)
* synthetic flow details per child
* basis reconciliation summary
* lot mapping summary per policy
* cash-in-lieu details including:

  * product leg (fractional qty, basis, realized pnl)
  * cash leg (ADJUSTMENT)
* completion status

---

## 18. Worked Example A: Mandatory Exchange (no cash)

Client holds:

* 100 shares of `OLDCO`
* source cost basis = USD 10,000

Upstream sends:

* exchange into 50 shares of `NEWCO`
* prices on effective date:

  * `OLDCO` price = 100
  * `NEWCO` price = 200

### Child 1 — source close

* `transaction_type = EXCHANGE_OUT`
* qty removed = 100
* synthetic outflow = `-(100 × 100) = -10,000`

### Child 2 — target add

* `transaction_type = EXCHANGE_IN`
* qty received = 50
* synthetic inflow = `+(200 × 50) = +10,000`

Result:

* source line closed with proper synthetic outflow base
* target line opened with proper synthetic inflow base
* position performance/contribution does not show 100% artifacts

---

## 19. Worked Example B: Merger with fractional cash-in-lieu

Client holds:

* 75 shares of `SRC`
* basis = USD 9,000

Upstream sends:

* target entitlement = 37.5 shares of `TGT`
* 37 shares delivered
* 0.5 settled as cash-in-lieu
* prices at event:

  * `TGT` price = 200
* cash-in-lieu proceeds = USD 110 (example)

### Child 1 — MERGER_OUT

* remove 75 `SRC`
* synthetic outflow uses source MVT (per provided price)

### Child 2 — MERGER_IN

* add 37 `TGT`
* synthetic inflow = `+(200 × 37) = +7,400`

### Child 3 — CASH_IN_LIEU (product leg)

* fractional qty = 0.5
* fractional MVT = `200 × 0.5 = 100`
* allocate basis to fractional portion (policy or upstream-provided)
* realized pnl = proceeds - allocated basis (capital + fx)

### Child 4 — ADJUSTMENT (cash leg)

* cash inflow = +110 into cash account
* linked to cash-in-lieu product leg

---

## 20. Test Matrix (Minimum)

Implementation is not complete unless these are covered:

### 20.1 Orchestration tests

* parent must exist before children finalize
* `*_OUT` must be processed before `*_IN`
* dependency graph blocks invalid order
* event not marked complete while dependencies remain

### 20.2 Synthetic flow tests

* source synthetic outflow = `-(price×qty_removed)` at effective date
* target synthetic inflow = `+(price×qty_received)` at effective date
* synthetic flows do not affect cash balances
* synthetic flows excluded from portfolio-level funding flows

### 20.3 Basis tests

* basis transferred out of source and into target
* basis conserved within tolerance
* residual basis behavior respects policy

### 20.4 Lot/held-since tests

* target lots map to source lots per policy
* held-since preserved per policy

### 20.5 Cash-in-lieu tests

* cash-in-lieu produces product leg + ADJUSTMENT cash leg
* basis allocated to fractional portion
* realized pnl computed and split correctly
* no double counting between product leg analytics and cash leg

### 20.6 Idempotency/replay tests

* parent replay does not duplicate child effects
* child replay does not duplicate synthetic flows or basis transfer
* cash leg replay does not duplicate cash settlement

---

## 21. Configurable Policies

The following must be configurable and versioned:

* price sourcing for synthetic flows (upstream vs market data)
* FX sourcing for base conversion
* missing price/FX behavior (park vs hard fail)
* lot continuity policy and held-since inheritance
* basis reconciliation tolerance
* residual source handling
* dependency enforcement strictness
* idempotency key strictness
* cash-in-lieu basis allocation method (if not supplied upstream)

Every processed event must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 22. Final Authoritative Statement

This RFC is the canonical specification for **Full Replacement Corporate Action Transfer** processing in lotus-core.

It standardizes:

* parent-child orchestration for full replacement events
* `*_OUT` / `*_IN` transaction semantics for source close and target add
* full basis transfer and reconciliation
* mandatory **position-level synthetic flows** at **MVT** for correct position performance/contribution analytics
* correct cash-in-lieu processing with product leg + `ADJUSTMENT` cash leg and no double counting
* deterministic ordering, idempotency, replay safety, and operationally safe event states
