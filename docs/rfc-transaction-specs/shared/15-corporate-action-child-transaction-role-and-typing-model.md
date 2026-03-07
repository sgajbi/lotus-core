# Corporate Action Child Transaction Role and Typing Model

## 1. Purpose

This document defines the shared child-transaction model for corporate actions in lotus-core.

It standardizes how lotus-core must represent, classify, and process the **child transactions** that arrive from upstream as part of a larger corporate action event.

This document is the shared source of truth for:

* child transaction roles
* child transaction typing
* source vs target leg semantics
* dependency expectations
* corporate-action-specific transaction classification
* consistent downstream handling across positions, cost basis, cash, income, and time series

All corporate action RFCs must reference this document.

---

## 2. Core Principle

A corporate action is processed as:

* one **parent corporate action event**, and
* one or more **child transactions**

The parent event provides:

* orchestration context
* grouping
* processing category
* dependency boundary

The child transactions provide the actual economic effects.

Each child transaction must be modeled with:

1. a **corporate-action child role**
2. a **transaction type**
3. a **dependency position**
4. clear source / target instrument semantics

---

## 3. Scope

This shared model applies to corporate actions that create dependent child transactions affecting:

* source holdings
* target holdings
* cost basis
* cash consideration
* cash in lieu
* fees
* taxes
* reporting / classification

This is especially important for:

* mergers
* exchanges
* spin-offs
* demergers
* split-offs
* security replacements
* mixed stock + cash events

---

## 4. Non-Goal

This document does not define:

* entitlement calculations
* ratio calculation logic
* election logic
* tax law determination
* event announcement mastering

Those are handled upstream.

---

## 5. Shared Modeling Rule

Every child transaction in a corporate action event must have **both**:

* a **generic child role** describing what it does economically
* a **specific transaction type** describing the booked transaction semantics

This distinction is mandatory.

### 5.1 Why both are needed

The **child role** gives reusable processing semantics across event families.

The **transaction type** gives domain-specific booking meaning for downstream engines, audit, and reporting.

Example:

A spin-off target leg may have:

* `child_role = TARGET_POSITION_ADD`
* `transaction_type = SPIN_IN`

This lets the engine reuse common logic while preserving business meaning.

---

## 6. Canonical Child Roles

The following child roles are shared and reusable across all corporate action families.

## 6.1 `SOURCE_POSITION_REDUCE`

Represents a reduction in the source instrument’s economic position.

Used when:

* source quantity reduces
* source cost basis reduces
* partial transfer out occurs

May or may not reduce actual quantity depending on the corporate action.

## 6.2 `SOURCE_POSITION_CLOSE`

Represents a full closure/extinguishment of the source instrument.

Used when:

* source position is fully replaced
* old line ceases to exist in the portfolio after the event

## 6.3 `TARGET_POSITION_ADD`

Represents creation or increase of the target instrument position.

Used when:

* new target holding is created
* replacement shares are booked
* spun-off shares are booked

## 6.4 `COST_BASIS_REALLOCATE`

Represents explicit basis transfer or basis split logic.

This may be:

* a physically separate child transaction, or
* a logical role implied within source and target child transactions

Even if not separately booked, lotus-core must treat basis reallocation as a distinct logical processing step.

## 6.5 `CASH_CONSIDERATION`

Represents a true cash consideration leg of the corporate action.

Examples:

* merger cash proceeds
* cash boot in a mixed consideration event

## 6.6 `CASH_IN_LIEU`

Represents a cash settlement for a fractional entitlement that cannot be delivered as a full unit.

Examples:

* fractional share cash in lieu in a merger
* fractional spin-off entitlement settled in cash

## 6.7 `CHARGE`

Represents a related fee/expense leg.

Examples:

* corporate action processing fee
* custody handling fee linked to the event

## 6.8 `TAX`

Represents a tax-related leg linked to the event.

Examples:

* withholding on cash component
* levy on reorganization settlement

## 6.9 `CLASSIFICATION_ADJUSTMENT`

Represents a non-position informational reclassification required for downstream reporting.

Examples:

* non-taxable reorganization marker
* income/non-income classification support record

## 6.10 `EVENT_COMPLETION_MARKER`

Represents an explicit upstream completion marker where such a record exists.

This is optional and must not be used as a substitute for actual dependency completion checks.

---

## 7. Child Transaction Typing Model

## 7.1 Typing principle

Transaction types for corporate action child transactions should be **event-family specific**, not generic transfer types.

This is mandatory for clarity, auditability, and downstream correctness.

For example:

* use `SPIN_OFF` / `SPIN_IN`
* do not overload `TRANSFER_OUT` / `TRANSFER_IN`

unless the event is genuinely a non-corporate-action transfer.

## 7.2 Why generic transfer types are not sufficient

Generic transfer types are too broad and lose critical meaning:

* they do not tell downstream systems that the movement came from a corporate action
* they do not distinguish corporate-action-specific basis semantics
* they make reporting and support less precise
* they blur the distinction between custody transfers and corporate reorganizations

---

## 8. Shared Typing Pattern

The standard pattern for corporate-action child transaction types is:

* **outgoing/source-side leg** = event-family-specific `*_OUT` or source-side named type
* **incoming/target-side leg** = event-family-specific `*_IN` or target-side named type

### 8.1 Examples

* spin-off:

  * `SPIN_OFF`
  * `SPIN_IN`

* merger exchange:

  * `MERGER_OUT`
  * `MERGER_IN`

* mandatory share exchange:

  * `EXCHANGE_OUT`
  * `EXCHANGE_IN`

* demerger:

  * `DEMERGER_OUT`
  * `DEMERGER_IN`

* split-off:

  * `SPLIT_OFF`
  * `SPLIT_IN`

* security replacement:

  * `REPLACEMENT_OUT`
  * `REPLACEMENT_IN`

This is the preferred shared standard.

---

## 9. Standard Mapping Between Child Role and Transaction Type

The following mapping is the default expectation.

| Child Role                  | Typical Transaction Type Pattern                                |
| --------------------------- | --------------------------------------------------------------- |
| `SOURCE_POSITION_REDUCE`    | `*_OUT` or source-side named type                               |
| `SOURCE_POSITION_CLOSE`     | `*_OUT` or source-side named type                               |
| `TARGET_POSITION_ADD`       | `*_IN` or target-side named type                                |
| `COST_BASIS_REALLOCATE`     | Separate typed basis transaction or embedded logical step       |
| `CASH_CONSIDERATION`        | Event-specific cash consideration type or standard cash CA type |
| `CASH_IN_LIEU`              | `CASH_IN_LIEU`                                                  |
| `CHARGE`                    | `FEE`                                                           |
| `TAX`                       | `TAX`                                                           |
| `CLASSIFICATION_ADJUSTMENT` | Event-specific or shared classification type                    |
| `EVENT_COMPLETION_MARKER`   | Event marker / metadata type if supported                       |

---

## 10. Standard Source / Target Interpretation

Every child transaction in a transfer-style corporate action must support:

* `source_instrument_id`
* `target_instrument_id`

### 10.1 Source interpretation

`source_instrument_id` = the instrument from which quantity, economic value, or cost basis originates.

### 10.2 Target interpretation

`target_instrument_id` = the instrument to which quantity, economic value, or cost basis is assigned.

### 10.3 Source-side child rule

For source-side children:

* `source_instrument_id` is mandatory
* `target_instrument_id` is strongly recommended if the transfer destination is known

### 10.4 Target-side child rule

For target-side children:

* both `source_instrument_id` and `target_instrument_id` should be populated
* this preserves directional lineage and basis provenance

---

## 11. Standard Parent / Child Linkage Fields

All child transactions should support the following shared fields:

* `parent_event_reference`
* `child_sequence_hint`
* `dependency_reference_ids`
* `source_transaction_reference`
* `target_transaction_reference`

These are orchestration fields, not direct economic measures.

### 11.1 `parent_event_reference`

Groups all child transactions under the same parent corporate action event.

### 11.2 `child_sequence_hint`

An upstream sequencing hint. Helpful, but not authoritative over dependency rules.

### 11.3 `dependency_reference_ids`

Explicit child references that must be completed first.

This is the strongest sequencing signal.

### 11.4 `source_transaction_reference`

Identifies the source-side child transaction in the event.

### 11.5 `target_transaction_reference`

Identifies the target-side child transaction in the event.

---

## 12. Standard Dependency Rules

## 12.1 Parent-first rule

No child transaction may be finalized before the parent event context is established.

## 12.2 Source-before-target default rule

For most transfer-style corporate actions, the default dependency is:

* source-side child first
* target-side child after source-side child

unless an event-specific RFC explicitly defines a different safe order.

## 12.3 Basis-before-completion rule

No event may be marked complete until basis transfer / allocation is resolved.

## 12.4 Fractional-cash-after-quantity rule

`CASH_IN_LIEU` must be processed only after the final deliverable target quantity is known.

---

## 13. Standard Child Transaction Invariants

Every corporate-action child transaction must satisfy:

* it belongs to exactly one parent corporate action event
* its role is explicit
* its transaction type is explicit
* its dependency status is explicit
* source/target direction is recoverable
* replaying the parent event must not duplicate the child effect
* the child must be safe to evaluate in the context of the full event graph

---

## 14. Downstream Interpretation Rules

Downstream systems should interpret child transactions as follows:

* **Position engine** → source and target position legs by resolved execution order
* **Cost basis engine** → basis reallocation after dependency-safe source/target resolution
* **Cash engine** → `CASH_CONSIDERATION`, `CASH_IN_LIEU`, `FEE`, `TAX`
* **Income engine** → only where event semantics explicitly create income-like components
* **Time series engine** → only completed, dependency-safe event states
* **Reporting / support** → both child role and transaction type should remain visible

---

## 15. Recommended Initial Transaction Types to Standardize

The first high-priority transaction-type pairs to standardize are:

* `SPIN_OFF` / `SPIN_IN`
* `MERGER_OUT` / `MERGER_IN`
* `EXCHANGE_OUT` / `EXCHANGE_IN`
* `REPLACEMENT_OUT` / `REPLACEMENT_IN`
* `CASH_IN_LIEU`

These cover most transfer-style corporate action patterns.

---

## 16. Final Authoritative Statement

Corporate action child transactions in lotus-core must be modeled using:

* an explicit **child role**
* an explicit **corporate-action-specific transaction type**
* explicit **parent-child linkage**
* explicit **dependency semantics**

This document is the shared source of truth for that model.
