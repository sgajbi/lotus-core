# RFC-CA-RIGHTS-ISSUE-FAMILY-01 Canonical Rights Issue Family Corporate Action Specification (Announce → Allocate → Elect → Subscribe/Renounce/Sell → Settle)

## 1. Document Metadata

* **Document ID:** RFC-CA-RIGHTS-ISSUE-FAMILY-01
* **Title:** Canonical Rights Issue Family Corporate Action Specification (Announce → Allocate → Elect → Subscribe/Renounce/Sell → Settle)
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                             |
| ------- | ----- | ------ | --------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical rights issue family specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing the **Rights Issue family** of corporate actions in lotus-core.

Rights actions are operationally complex because they span multiple lifecycle steps and may result in different outcomes depending on client election and execution:

* **rights entitlement allocation** (rights appear as an instrument/position)
* **client election** (subscribe, sell/renounce, allow lapse, oversubscribe)
* **settlement**:

  * subscribe → new shares delivered + cash paid (subscription cost)
  * sell/renounce → cash received (sale proceeds)
  * lapse → rights expire worthless
  * oversubscription → extra shares delivered and/or cash refund

**Important constraints (per your target model):**

* entitlement calculation and election decisioning are handled upstream (core banking/custody/OMS)
* lotus-core processes the resulting transaction set to correctly compute:

  * positions
  * cost basis
  * cash movements
  * income/expense where applicable
  * time series
  * position-level performance/contribution consistency

Rights issue processing must be deterministic, auditable, replay-safe, and compatible with `RFC-CA-REVERSAL-01`.

---

## 3. Scope

This RFC applies to rights issue and similar events where upstream delivers a sequence of related transactions representing:

* entitlement creation
* election outcome execution
* share delivery and cash settlement
* rights disposal/expiry
* refunds or adjustments

### 3.1 Rights issue patterns covered

* **Transferable rights** (rights can be sold in market)
* **Non-transferable rights** (cannot be sold; can be subscribed or lapse)
* **Nil-paid rights** / rights trading period settlements
* **Oversubscription** (extra allocation)
* **Partial subscription** (subscribe some, sell/renounce/lapse rest)
* **Cash alternative election** (if upstream models as rights sell/renounce + cash)

### 3.2 Out of scope

This RFC does not define:

* entitlement calculation logic (upstream)
* client election workflows (upstream)
* exchange trading venue integration for rights trading (upstream)
* tax law determination (policy/upstream)
* complex derivative rights (warrants) unless explicitly modeled as rights instruments (can be added later)

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/14-corporate-action-processing-model.md`
* `shared/15-corporate-action-child-transaction-role-and-typing-model.md`
* `shared/07-accounting-cash-and-linkage.md`
* `shared/16-position-level-synthetic-flows-for-corporate-actions.md` (only where synthetic position flows are required for position analytics)
* `RFC-CA-REVERSAL-01` (cancel/correct/rebook handling)

---

## 5. Definitions

### 5.1 Parent security vs rights instrument vs new shares

* **Parent security**: the existing equity instrument held before the rights event
* **Rights instrument**: a (temporary) instrument representing the entitlement (transferable or not)
* **Subscription shares**: newly issued shares delivered upon subscription (typically same as parent security or a new line of the same issuer)

### 5.2 Lifecycle dates (as provided upstream)

* `announcement_date`
* `record_date`
* `ex_date`
* `subscription_start_date`
* `subscription_end_date`
* `rights_trading_start_date` / `rights_trading_end_date` (if transferable)
* `payment_date`
* `allotment_date`
* `listing_date` (if applicable)

Lotus-core stores these for audit; processing uses `effective_date` per child/event.

### 5.3 Election outcomes (as delivered upstream)

* `SUBSCRIBE`
* `SELL` / `RENONCE`
* `LAPSE`
* `OVERSUBSCRIBE`
* `CASH_ALTERNATIVE` (if modeled as cash outcome)
* `MIXED` (subscribe part, sell/lapse part)

---

## 6. Core Invariants

After completion of a rights event chain:

* rights entitlement positions must reconcile to outcomes:

  * subscribed rights are consumed into new shares
  * sold/renounced rights are consumed into cash proceeds
  * lapsed rights are consumed to zero with appropriate treatment
* cash movements must reconcile with subscription payments, sale proceeds, refunds
* cost basis must be consistent:

  * rights basis carried into subscribed shares where applicable
  * rights disposal/expiry realized P&L handled per policy
* event must remain auditable with parent-child linkage and deterministic ordering

---

## 7. Transaction Types Standardized in this RFC

This RFC standardizes canonical transaction types (child types). Upstream may send different raw types; lotus-core must map to these canonical types.

### 7.1 Entitlement / rights lifecycle

* `RIGHTS_ANNOUNCE` (optional informational marker; may be stored as parent metadata instead)
* `RIGHTS_ALLOCATE` (create rights instrument position)
* `RIGHTS_EXPIRE` (rights lapse/expire worthless)
* `RIGHTS_ADJUSTMENT` (rare entitlement adjustments; correction-like, not cancel)

### 7.2 Rights disposal / election execution

* `RIGHTS_SELL` (rights sold / renounced for proceeds)
* `RIGHTS_SUBSCRIBE` (rights exercised/subscribed; leads to share delivery + subscription cash payment)
* `RIGHTS_OVERSUBSCRIBE` (extra exercise; results in extra share delivery + extra cash paid and/or refunds)
* `RIGHTS_REFUND` (refund unused subscription cash, oversubscription refund, or allocation change)

### 7.3 Share delivery

* `RIGHTS_SHARE_DELIVERY` (new shares delivered as a result of exercise)

  * target instrument may be same as parent security or a new line

### 7.4 Cash legs (real cash movements)

* `ADJUSTMENT` (cash instrument) — used for:

  * subscription cash outflow
  * sale proceeds inflow
  * refunds inflow
  * fee/tax postings if provided as cash legs

### 7.5 Optional

* `FEE`
* `TAX`

---

## 8. Parent Event Model

A rights issue must be represented by a parent corporate action event.

### 8.1 Required parent fields

* `corporate_action_event_id`
* `corporate_action_type = RIGHTS_ISSUE`
* `processing_category = RIGHTS_ISSUE_FAMILY`
* `event_status`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 8.2 Recommended parent fields

* parent security instrument id (`parent_security_instrument_id`)
* rights instrument id (`rights_instrument_id`)
* subscription security instrument id (`subscription_security_instrument_id`)
* lifecycle dates (Section 5.2)
* entitlement ratio metadata (if provided)
* `transferable_rights: bool`

---

## 9. Orchestration and Linkage Fields (Mandatory)

Each child must support:

* `parent_event_reference`
* `child_sequence_hint` (recommended)
* `dependency_reference_ids` (recommended)
* `child_transaction_reference` (unique within event)
* `source_instrument_id`
* `target_instrument_id` (for transfers/deliveries)
* `related_rights_reference_id` (ties all rights legs together; recommended)

### 9.1 Required linkage for cash legs

Cash legs (`ADJUSTMENT`) must be linked to the economic child they settle via:

* same `economic_event_id`
* same `linked_transaction_group_id`
* and a direct link:

  * `linked_cash_transaction_id` (recommended)
  * `linked_product_transaction_id` (recommended on the cash leg)

---

## 10. Processing Model (High Level)

Rights processing is a **chain** of related child transactions.

Lotus-core must not assume all legs arrive together. It must:

* accept partial arrivals
* enforce dependency order
* park when critical dependencies are missing (policy-driven)
* complete once the required chain is satisfied

---

## 11. Canonical Lifecycle Stages and Required Behaviors

### Stage A — Entitlement allocation (`RIGHTS_ALLOCATE`)

#### A.1 Semantics

* create/increase a position in the rights instrument
* record entitlement quantity (whole + fractional if supported)
* record any upfront rights basis if provided (rare; sometimes rights are cost-free initially)

#### A.2 Basis rule (policy-driven)

Default:

* rights entitlement has **zero cost basis** at allocation, unless upstream provides basis

Configurable:

* `rights_entitlement_basis_mode = ZERO | UPSTREAM_PROVIDED | DERIVED_FROM_PARENT` (last is rare)

#### A.3 Position/performance rule

Rights are a new instrument position. Performance starts from its own valuation series.
No synthetic transfer flows are required by default for rights allocation.

---

### Stage B — Election outcome execution

Upstream provides the outcome as concrete child transactions. lotus-core must process whichever combination arrives.

#### B.1 Subscribe (`RIGHTS_SUBSCRIBE` + `RIGHTS_SHARE_DELIVERY` + cash outflow)

**Required child set for a subscription outcome:**

1. `RIGHTS_SUBSCRIBE` (consume rights quantity)
2. `RIGHTS_SHARE_DELIVERY` (deliver new shares)
3. `ADJUSTMENT` cash leg (subscription payment outflow)

**Processing:**

* reduce rights position by exercised quantity
* increase subscription shares position by delivered quantity
* post cash outflow for subscription cost
* allocate basis:

  * subscription shares basis = (subscription cash paid) + (rights basis consumed, if any) + (fees/taxes if policy includes in basis)
* realized P&L:

  * none by default on exercise (policy-driven; normally not realized)

**Position-level synthetic flows (optional, policy-driven):**

* not required for portfolio, but for position analytics some banks want to treat exercise like a buy of new shares.
  If enabled:
* create synthetic inflow on subscription shares at MVT (or subscription price × qty) purely for position performance base.
  This must be explicitly controlled by:
* `rights_subscription_synthetic_flow_mode = NONE | SUBSCRIPTION_PRICE_X_QTY | MVT_PRICE_X_QTY`

Default: `NONE` (because actual cash outflow exists and will support performance if your position engine uses cashflows).

#### B.2 Sell / Renounce (`RIGHTS_SELL` + cash inflow)

**Required child set for a sell outcome:**

1. `RIGHTS_SELL` (consume rights quantity)
2. `ADJUSTMENT` cash leg (sale proceeds inflow)

**Processing:**

* reduce rights position by sold quantity
* post cash inflow proceeds
* compute realized P&L on rights disposal (policy-driven):

  * realized capital pnl = proceeds - rights_cost_basis_sold
  * rights_cost_basis_sold is often zero unless basis exists
* FX split if cross-currency per standard realized FX model

#### B.3 Lapse / Expire (`RIGHTS_EXPIRE`)

**Required child set:**

* `RIGHTS_EXPIRE` consuming remaining rights quantity to zero

**Processing:**

* reduce rights quantity to zero
* realized P&L:

  * if rights basis is non-zero, expire may create realized loss (policy-driven)
  * otherwise no pnl
* no cash leg

#### B.4 Oversubscription (`RIGHTS_OVERSUBSCRIBE` + delivery + cash + refund)

Possible child set:

* extra subscribe leg
* extra cash payment
* later `RIGHTS_REFUND` + cash inflow (refund)
* delivery legs for extra shares if allocated

**Processing:**

* treat oversubscription as additional subscription attempts
* if refunded:

  * post refund cash inflow
  * adjust basis allocation accordingly
* ensure cash paid - cash refunded reconciles to final shares delivered

---

## 12. Cost Basis Rules (Rights, Subscription Shares, and Disposal)

### 12.1 Rights cost basis

Default:

* rights basis at allocation = 0
* rights basis may become non-zero if:

  * upstream assigns basis
  * rights purchased via market buy (not in scope of CA; handled as BUY)

### 12.2 Subscription shares basis

For delivered shares from rights exercise:

`basis_subscription_shares = subscription_cash_paid + rights_basis_consumed + basis_includable_fees_taxes`

Policy controls whether to include fees/taxes in basis.

### 12.3 Rights disposal realized P&L (sell/expire)

If rights are sold or expire and rights basis is non-zero:

`realized_capital_pnl = proceeds (or 0 for expire) - rights_basis_disposed`

FX P&L computed separately if cross-currency.

---

## 13. Cash Leg Rules (Dual Accounting)

All actual cash movements must be recorded as `ADJUSTMENT` legs against the cash instrument.

Cash movements include:

* subscription payment outflows
* rights sale proceeds inflows
* refunds inflows
* fees/taxes cash legs if posted separately

Cash legs must be linked to the economic child they settle.

---

## 14. Lot and Held-Since Rules

### 14.1 Rights lots

Rights positions may be tracked as a single lot or multiple lots depending on source. At minimum:

* create lots for rights if your system is lot-aware for equities

### 14.2 Subscription shares lots

New shares delivered must create lots. Held-since policy is configurable:

* `RIGHTS_DELIVERY_HELD_SINCE_POLICY = DELIVERY_DATE | ORIGINAL_PARENT_HELD_SINCE` (bank-specific)

Recommended default:

* `DELIVERY_DATE` (since these are newly acquired shares by subscription)

If banks require inherited holding period, it must be explicit and auditable.

### 14.3 Lot basis allocation

Allocate basis to delivered share lots proportionally to delivered quantities unless upstream provides lot-level allocation.

---

## 15. Processing Order and Dependencies

Default dependency-safe order:

1. register parent event
2. apply `RIGHTS_ALLOCATE` (if present)
3. apply election outcomes:

   * subscription chain:

     * `RIGHTS_SUBSCRIBE` → `RIGHTS_SHARE_DELIVERY` → cash `ADJUSTMENT` outflow
   * sell chain:

     * `RIGHTS_SELL` → cash `ADJUSTMENT` inflow
   * expire chain:

     * `RIGHTS_EXPIRE`
4. apply refunds (`RIGHTS_REFUND` → cash `ADJUSTMENT` inflow)
5. apply optional `FEE` and `TAX`
6. reconcile and mark event complete

Event completion must be policy-driven:

* strict mode requires all expected legs for the chosen election outcome(s)
* tolerant mode allows late-arriving refunds and keeps event open until SLA expires

---

## 16. Event States

Use standard CA event states:

* `PENDING_CHILDREN`
* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `PARKED`
* `FAILED`
* `COMPLETED`

Additionally recommended rights-specific status markers (optional):

* `AWAITING_ELECTION_OUTCOME`
* `AWAITING_SETTLEMENT_CASH`
* `AWAITING_DELIVERY`

---

## 17. Idempotency and Replay

### 17.1 Parent idempotency key

Example:

* `(source_system, parent_event_reference, portfolio_id)`

### 17.2 Child idempotency key

* `(parent_event_reference, child_transaction_reference)`

### 17.3 Replay rule

Replays must not duplicate:

* rights allocations
* subscription deliveries
* cash postings
* refunds
* realized pnl computations

---

## 18. Validation Rules

Must validate:

* parent event exists and is `RIGHTS_ISSUE_FAMILY`
* rights instrument id and parent security id are consistent where provided
* rights quantity reconciliation:

  * rights allocated = rights consumed by subscribe + rights sold + rights expired + rights remaining (0 if completed)
* cash reconciliation:

  * subscription cash outflow aligns to subscription qty × subscription price (within tolerance) when provided
  * sale proceeds align to provided trade confirmations (within tolerance) when provided
  * refunds reconcile to oversubscription outcomes (within tolerance)

Hard-fail unless policy override:

* missing cash leg for a subscription chain when required
* missing delivery leg for a subscription chain when required
* rights consumed beyond available rights quantity
* unreconcilable rights quantity mismatch beyond tolerance

---

## 19. Output Contract

Expose:

* parent rights event with lifecycle dates and key ids
* rights allocation view (rights qty, basis mode)
* election outcome legs (subscribe/sell/expire/refund)
* delivered shares view (qty, lots, basis)
* cash legs (subscription, proceeds, refunds) with linkage
* realized P&L for rights disposal where applicable (capital + FX)
* completion status and reconciliation summaries

---

## 20. Worked Examples

### 20.1 Example A: Transferable rights, sell all

* Parent holding: 1,000 shares
* Rights entitlement: 100 rights
* Rights sold: 100 rights, proceeds 250
* Rights basis at allocation: 0

Results:

* rights qty goes 100 → 0
* cash +250
* realized pnl on rights = 250 - 0 = 250 (capital)

### 20.2 Example B: Subscribe partially, sell remainder

* Rights allocated: 100
* Subscribe: 60 rights → deliver 60 shares, subscription cost 600
* Sell: 40 rights → proceeds 80
* Rights basis: 0

Results:

* cash outflow 600, cash inflow 80 (net -520)
* new shares +60 with basis 600
* rights position ends at 0
* rights disposal pnl for sold rights = 80

### 20.3 Example C: Oversubscription with refund

* Rights allocated: 100
* Subscribe: 100 + oversubscribe attempt 50
* Cash paid: 1,500
* Allocated extra shares: 120 total delivered
* Refund: 300

Results:

* net cash paid = 1,200
* delivered shares basis = 1,200 (plus any fees if included)
* refund posted as separate cash leg linked to refund child

---

## 21. Test Matrix (Minimum)

* rights allocation creates rights position with correct quantity and basis mode
* subscribe chain: consume rights, deliver shares, post cash outflow, assign basis correctly
* sell chain: consume rights, post cash inflow, compute realized pnl (including FX where relevant)
* expire chain: consume rights to zero, compute loss if basis non-zero per policy
* oversubscription + refund reconciles cash and delivered shares
* partial subscribe + sell reconciles rights quantities
* idempotency: replay does not duplicate any effects
* reversal/correction via `RFC-CA-REVERSAL-01` restores pre-event state and rebooks correctly

---

## 22. Configurable Policies

Must be configurable and versioned:

* strictness of lifecycle completeness (`STRICT` vs `ALLOW_LATE_REFUNDS`)
* rights entitlement basis mode (`ZERO`, `UPSTREAM_PROVIDED`, `DERIVED_FROM_PARENT`)
* whether rights exercise creates synthetic position inflow for performance (`NONE`, `SUBSCRIPTION_PRICE_X_QTY`, `MVT_PRICE_X_QTY`)
* whether to include fees/taxes in subscription share basis
* rights disposal realized pnl mode (`UPSTREAM`, `DERIVE`, `NONE`)
* held-since policy for delivered shares (`DELIVERY_DATE` default)
* reconciliation tolerances
* idempotency strictness

All events must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 23. Final Authoritative Statement

This RFC defines the canonical specification for the **Rights Issue family** in lotus-core.

It standardizes:

* multi-stage rights lifecycle processing (allocate → subscribe/sell/expire → settle)
* deterministic dependency ordering and completeness rules
* correct handling of positions, basis, cash legs, and realized P&L
* auditable linkage across rights instruments, delivered shares, and cash movements
* replay safety and compatibility with `RFC-CA-REVERSAL-01`

If any implementation or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
