# Corporate Action Processing Model for Upstream-Calculated Events

## 1. Purpose

This document defines the shared conceptual model for processing **corporate action transactions** in lotus-core.

It standardizes how lotus-core must:

* accept corporate action transactions from upstream systems
* identify relationships between related transactions
* determine the correct processing order
* process parent and dependent transactions safely and deterministically
* preserve consistency for:

  * positions
  * cost basis
  * cash flows
  * income
  * time series

This document is a shared processing standard and must be referenced by all future corporate action RFCs.

---

## 2. Scope

This model applies to corporate actions where upstream systems already perform:

* event setup
* entitlement determination
* ratio calculation
* election outcome resolution
* quantity entitlement calculation

Lotus-core does **not** calculate entitlements.

Lotus-core is responsible only for consuming and processing the resulting transaction set so downstream portfolio analytics remain correct.

This shared model applies especially to corporate actions that produce:

* **quantity transfers**
* **cost-basis transfers**
* **cash proceeds / cash in lieu**
* **income-related adjustments**
* **instrument-to-instrument migrations**
* **multi-transaction dependent chains**

---

## 3. Non-Goals

Lotus-core does **not**:

* calculate shareholder eligibility
* calculate entitlement ratios
* perform election optimization
* determine issuer tax treatment
* source reference data for the action itself
* act as the event master for corporate action announcements

Those responsibilities belong upstream.

---

## 4. Core Principle

A corporate action must be processed as a **related transaction set**, not as isolated transactions.

Even when upstream sends multiple transactions separately, lotus-core must recognize that they belong to the same **corporate action event** and process them using an explicit dependency-aware model.

This is required because in many corporate actions:

* one transaction changes the source holding
* another creates or adjusts the target holding
* another moves cost basis
* another creates cash proceeds or cash in lieu
* another records income / tax / fee side effects

If these are processed independently or in the wrong order, the system can produce incorrect:

* positions
* remaining lots
* transferred basis
* realized values
* cash flows
* time series states

---

## 5. Canonical Event Structure

## 5.1 Parent event

Every related corporate action transaction set must be grouped under a logical **parent corporate action event**.

The parent event is the orchestration and dependency anchor.

The parent event must provide the shared identity for all child transactions.

The parent event is not necessarily a tradable transaction itself. It is the controlling event record.

## 5.2 Child transactions

Each economic effect of the corporate action is represented as one or more **child transactions**.

Examples of child effects:

* source position reduction
* source position closure
* target position creation
* target position increase
* cost-basis reallocation
* cash proceeds
* cash in lieu
* fee
* tax
* income classification adjustment

## 5.3 Child transactions are dependent

Child transactions may have dependencies on other child transactions.

Examples:

* a target-position transaction may depend on a source-position reduction being processed first
* a cash-in-lieu transaction may depend on final fractional quantity resolution
* a cost-basis allocation transaction may depend on all resulting target quantities being known

Therefore lotus-core must not treat child transactions as unordered.

---

## 6. What Lotus-Core Must Solve

Given an upstream corporate action transaction set, lotus-core must:

1. identify all transactions belonging to the same corporate action event
2. classify each child transaction by its economic role
3. determine dependencies between them
4. derive a valid processing sequence
5. execute them in a deterministic order
6. ensure the resulting state is consistent for:

   * positions
   * lots
   * cost basis
   * cash
   * income
   * time series

This is the core responsibility.

---

## 7. Required Shared Identifiers

Every corporate action transaction entering lotus-core must support grouping and dependency resolution.

## 7.1 Mandatory event identifiers

At minimum, the model must support:

* `corporate_action_event_id`
* `corporate_action_type`
* `economic_event_id`
* `linked_transaction_group_id`

## 7.2 Recommended upstream linkage identifiers

To support reliable orchestration, upstream payloads should also provide, where available:

* `parent_event_reference`
* `child_sequence_hint`
* `dependency_reference_ids`
* `source_instrument_id`
* `target_instrument_id`
* `source_transaction_reference`
* `target_transaction_reference`

## 7.3 Internal dependency identifiers

Lotus-core should enrich incoming transactions with internal dependency metadata such as:

* `processing_node_id`
* `depends_on_node_ids`
* `processing_stage`
* `resolved_execution_order`

---

## 8. Canonical Processing Roles

Each child transaction in a corporate action set must be classified into one of a small number of canonical processing roles.

## 8.1 Source position role

Represents the transaction that reduces, closes, or otherwise modifies the original/source instrument holding.

Examples:

* full removal of old security
* partial reduction of parent security
* reduction of tendered quantity

## 8.2 Target position role

Represents the transaction that creates or increases the resulting/target instrument holding.

Examples:

* creation of acquirer shares
* creation of spun-off shares
* increase in replacement share line

## 8.3 Cost-basis transfer role

Represents basis transfer or reallocation logic.

This may be explicit in the incoming payload, or implicit in the semantics of the related child transactions, but lotus-core must still process it as a distinct logical step.

Examples:

* full basis transfer from old security to new security
* partial basis split between retained parent and new child
* multi-target allocation

## 8.4 Cash settlement role

Represents cash created by the corporate action.

Examples:

* merger cash consideration
* cash in lieu for fractions
* mandatory cash payout component

## 8.5 Charge / tax role

Represents related fee or tax side effects.

Examples:

* withholding on cash component
* stamp duty on reorganization leg
* corporate-action processing fee

## 8.6 Informational / classification role

Represents non-position, non-cash updates needed for correct reporting.

Examples:

* income classification tagging
* non-realizing reclassification marker
* event completion marker

---

## 9. Processing Order Model

## 9.1 Parent-first rule

The parent corporate action event must be registered and validated first.

This is mandatory.

The parent event establishes:

* grouping
* event type
* source-target relationships
* dependency context
* orchestration boundary

No child transaction may be finalized before the parent event context exists.

## 9.2 Dependency-driven child execution

After parent registration, child transactions must be processed according to dependency order, not arrival order.

Arrival order from upstream must not be assumed to be safe.

## 9.3 Canonical execution order

For most transfer-style corporate actions, the default logical order is:

1. register parent event
2. validate full child set / minimum required dependency set
3. process source position adjustment
4. process target position creation / increase
5. process cost-basis transfer / allocation finalization
6. process cash settlement components
7. process fee / tax components
8. mark event complete

This is the default shared pattern.

A transaction-specific RFC may refine this order, but must not violate dependency correctness.

## 9.4 Atomicity boundary

The platform must define whether the event is processed as:

* fully atomic across all child transactions, or
* staged but dependency-safe with recoverable intermediate state

At minimum, lotus-core must prevent downstream consumers from treating a partially processed event as complete.

---

## 10. State and Consistency Rules

## 10.1 Incomplete event rule

A corporate action event must remain in an explicit **incomplete** state until all required dependent child transactions have been processed or intentionally waived by policy.

## 10.2 No unsafe partial finalization

The system must not expose a final “completed” portfolio state for the event while:

* source quantity is reduced but target quantity not yet created
* target quantity exists but cost basis has not yet been allocated
* cash component is posted before dependency resolution is complete
* charges/taxes are applied before the dependent economic basis exists

## 10.3 Intermediate visibility rule

If staged processing is used, intermediate states must be visible as explicitly transitional, such as:

* `PENDING_DEPENDENCIES`
* `PARTIALLY_APPLIED`
* `AWAITING_COST_ALLOCATION`
* `AWAITING_CASH_COMPONENT`
* `COMPLETED`

---

## 11. Shared Corporate Action Categories

Corporate actions should be grouped by **processing pattern**, not only by market label.

This allows reusable orchestration logic.

## 11.1 Category A: Full replacement transfer

The source instrument is fully replaced by one or more target instruments.

Typical examples:

* stock-for-stock merger
* mandatory exchange
* share line replacement
* redomiciliation / new ISIN replacement

Processing shape:

* source position fully closed
* target position created
* full cost basis transferred
* optional fractional cash may exist

## 11.2 Category B: Partial transfer with source retained

Only part of the original economic value or cost basis moves to a new instrument, while the source remains.

Typical examples:

* spin-off
* demerger
* some split-offs

Processing shape:

* source remains open
* target position created
* basis split across retained source and target
* optional fractional cash may exist

## 11.3 Category C: Full replacement with cash component

The source instrument is fully replaced, but the holder receives both target security and cash.

Typical examples:

* merger with stock + cash
* scheme of arrangement with mixed consideration

Processing shape:

* source fully closed
* target created
* basis allocated across target security and cash component
* optional realized/tax treatment may apply by policy

## 11.4 Category D: Partial transfer with cash component

Part of the economic value moves to a new instrument, and there is also a cash component.

Typical examples:

* partial exchange with cash boot
* complex reorganization with retained parent and cash payout

Processing shape:

* source remains or partially reduces
* target created
* basis split across source, target, and cash

## 11.5 Category E: Multi-target allocation transfer

One source instrument allocates into multiple target instruments.

Typical examples:

* multi-entity demerger
* complex restructuring creating multiple resulting lines

Processing shape:

* one source
* multiple targets
* basis allocated across multiple targets
* source may remain or be extinguished

## 11.6 Category F: Fractional cash settlement overlay

A transfer event includes a fractional entitlement that cannot be delivered in full shares and is settled in cash.

Typical examples:

* cash in lieu on merger ratio
* cash in lieu on spin-off fraction

Processing shape:

* overlays another category
* requires quantity rounding first
* then creates dependent cash transaction

This is an overlay category, not a standalone base category.

---

## 12. Categories That Typically Need This Model Most

The first corporate actions that should use this shared processing model are:

* **Merger (stock-for-stock)**
* **Merger (stock + cash)**
* **Mandatory share exchange / reorganization exchange**
* **Spin-off**
* **Demerger**
* **Split-off**
* **Security replacement / share line migration**
* **Any of the above with cash in lieu**

These are the highest-value patterns because they involve the hardest sequencing and basis-transfer problems.

---

## 13. Categories Usually Outside This Transfer Pattern

These are corporate actions, but they are usually not the same parent/child transfer model family:

* stock split
* reverse split
* bonus issue of same line
* stock dividend of same line
* ordinary cash dividend
* coupon / interest
* rights issue subscription
* pure cash tender
* simple name change with no economic effect

These should be modeled separately unless a future RFC explicitly brings them into this framework.

---

## 14. Canonical Processing Requirements

## 14.1 Grouping requirement

Lotus-core must be able to group all child transactions under the same parent corporate action event.

## 14.2 Dependency requirement

Lotus-core must be able to identify which child transactions depend on others.

## 14.3 Ordering requirement

Lotus-core must derive a deterministic execution order that is dependency-safe.

## 14.4 Replay requirement

The same event must be replay-safe at the parent-event level.

Reprocessing must not duplicate:

* source reductions
* target creations
* cost transfers
* cash proceeds
* charges/taxes

## 14.5 Idempotency requirement

Idempotency must be enforced at both:

* child transaction level, and
* parent corporate action event level

## 14.6 Completion requirement

An event is complete only when all required dependent child transactions have reached a terminal success state or an explicitly approved waived state.

---

## 15. Downstream Consumption Rules

Once processed, downstream systems should consume the resulting effects as follows:

* **Position engine** → source and target position transactions in resolved order
* **Cost basis engine** → basis transfer / allocation outcomes after dependency resolution
* **Cash engine** → cash proceeds / cash in lieu / related charges
* **Income engine** → classification outputs where the event creates income-like components
* **Time-series engine** → only dependency-safe state transitions, not unsafe partial completion
* **Reporting / reconciliation** → grouped parent event plus child transaction details

---

## 16. Failure Handling Model

## 16.1 Dependency failure

If a required predecessor child transaction fails, dependent child transactions must not be finalized.

## 16.2 Missing child transaction

If the minimum required transaction set for a given category is incomplete, the event must be parked or held in a pending state.

## 16.3 Partial processing

If partial application is allowed, the event must remain explicitly non-final and must be recoverable.

## 16.4 Recovery

Recovery must preserve:

* original parent-child linkage
* resolved execution order
* already-applied successful steps
* remaining dependent steps

---

## 17. Recommended Shared Data Model

The shared conceptual model should include at minimum:

### 17.1 Parent event model

* `corporate_action_event_id`
* `corporate_action_type`
* `processing_category`
* `event_status`
* `effective_date`
* `announcement_reference`
* `source_system`
* `economic_event_id`
* `linked_transaction_group_id`

### 17.2 Child relationship model

* `child_transaction_id`
* `child_role`
* `source_instrument_id`
* `target_instrument_id`
* `depends_on_transaction_ids`
* `processing_stage`
* `resolved_execution_order`
* `is_required_for_completion`

### 17.3 Processing status model

* `NOT_READY`
* `READY`
* `APPLIED`
* `PENDING_DEPENDENCIES`
* `FAILED`
* `PARKED`
* `COMPLETED`

---

## 18. Recommended Next RFC Layer

After this shared model, the next documents should be:

1. **Shared child transaction role model**
2. **Shared cost-basis transfer model for corporate actions**
3. **RFC for Full Replacement Transfer corporate actions**
4. **RFC for Partial Transfer with Source Retained**
5. **RFC for Fractional Cash in Lieu overlay**
6. **RFC for Mixed Stock + Cash corporate actions**

This avoids repeating orchestration logic in every event-specific RFC.

---

## 19. Final Authoritative Statement

For corporate actions handled in lotus-core, the platform must process related transactions as a **dependency-aware grouped event** under a parent corporate action context.

Lotus-core does not calculate entitlements, but it must correctly process the resulting transaction set in the correct dependency order so that positions, cost basis, cash flows, income, and time series remain correct and internally consistent.

This document is the shared source of truth for that processing model.
