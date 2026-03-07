# RFC 075 - Corporate Action Full Replacement Transfer Implementation Plan

**Status**: Draft  
**Date**: 2026-03-07  
**Owner**: *TBD*  
**Reviewers**: *TBD*  
**Approvers**: *TBD*  

## 1. Purpose

This document defines the implementation plan for **Full Replacement Corporate Action** processing in `lotus-core`, aligned to:

- `docs/rfc-transaction-specs/transactions/CA/RFC-CA-FULL-REPLACEMENT-01.md`
- `docs/rfc-transaction-specs/shared/14-corporate-action-processing-model.md`
- `docs/rfc-transaction-specs/shared/15-corporate-action-child-transaction-role-and-typing-model.md`
- `docs/rfc-transaction-specs/shared/16-position-level-synthetic-flows-for-corporate-actions.md`

The implementation must produce analytically correct position- and portfolio-level outputs while preserving event lineage and avoiding cashflow double counting.

## 2. Key Alignment Changes from Prior Draft

The updated CA documents require explicit handling of two distinct flow planes:

1. **Position transfer semantics**
   - `*_OUT` and `*_IN` legs are **product-position legs**.
   - They carry mandatory position-level synthetic flows (`POSITION_TRANSFER_OUT` / `POSITION_TRANSFER_IN`) based on MVT.
   - These flows are **never** portfolio-level funding flows.

2. **Cash settlement plane**
   - Real liquidity settlement is represented through an `ADJUSTMENT` cash transaction.
   - Fractional settlement use case (`CASH_IN_LIEU`) still requires both:
     - `CASH_IN_LIEU` product leg (fractional position economics and realized pnl)
     - linked `ADJUSTMENT` cash leg for real cash movement
   - Synthetic flow and cash leg must remain disjoint in all calculators.

3. **Dependency-safe orchestration**
   - Processing uses parent-child sequencing and explicit `CASH_IN_LIEU` dependency requirements.
   - Event-level completion is based on required legs plus explicit reconciliation checks, not arrival order.

## 3. Scope

### 3.1 Covered CA child type sets

- `MERGER_OUT` / `MERGER_IN`
- `EXCHANGE_OUT` / `EXCHANGE_IN`
- `REPLACEMENT_OUT` / `REPLACEMENT_IN`
- `CASH_IN_LIEU` (optional) with linked `ADJUSTMENT` cash leg
- optional `FEE`, `TAX`, `CHARGE`, `CLASSIFICATION_ADJUSTMENT` when supplied

### 3.2 Out of scope

- Non-full replacement CAs (spin-off, demerger, partial exchange/scheme variants unless represented as full replacement)
- Upstream entitlement calculation
- Jurisdictional tax law resolution (upstream/domain policy remains authoritative)

## 4. Canonical Cashflow/Analytics Design

### 4.1 Product legs

For all full replacement `*_OUT` and `*_IN` children:

- set `SyntheticFlowDetails.has_synthetic_flow = true`
- use valuation method `MVT_PRICE_X_QTY`
- set `synthetic_flow_effective_date` to parent effective date (or deterministic upstream date)
- set classification:
  - `POSITION_TRANSFER_OUT` for source leg
  - `POSITION_TRANSFER_IN` for target leg

These flows are not posted to portfolio cash accounts and must be ignored by TWR/flow funding checks.

### 4.2 Cash-in-lieu product and cash legs

When `CASH_IN_LIEU` is present:

- `CASH_IN_LIEU` leg remains a product leg with:
  - fractional quantity
  - fractional MVT
  - optional `POSITION_CASH_IN_LIEU_OUT` synthetic flow
  - realized P&L and basis allocation for fractional disposal
- cash settlement leg must be created/received as `ADJUSTMENT` on cash instrument and linked through CA fields (`parent_transaction_reference`, `economic_event_id`, and direct leg linkage where available).
- `ADJUSTMENT` is consumed by cashflow engine as a normal portfolio-level cash movement.

### 4.3 Non-negotiable separation rule

- A synthetic flow **cannot** be interpreted as portfolio cashflow.
- A real cash `ADJUSTMENT` cannot be interpreted as position synthetic flow.
- Any attempt to aggregate both into a single flow path for contribution/performance is a defect and must fail reconciliation.

## 5. End-to-End Data Model Direction

### 5.1 Parent event model (required)

- corporate action event table (`corporate_action_events`) or equivalent canonical parent
  - `corporate_action_event_id` (stable external event key)
  - `processing_category = FULL_REPLACEMENT_TRANSFER`
  - event status lifecycle (`PENDING_DEPENDENCIES`, `PENDING_CHILDREN`, `PARTIALLY_APPLIED`, `PARKED`, `FAILED`, `COMPLETED`)
  - processing fingerprints for replay/idempotency

### 5.2 Child transaction metadata extensions

All children must include:

- `parent_transaction_reference`
- `linked_parent_event_id`
- `linked_cash_transaction_id` for cash-in-lieu pairs (recommended)
- `child_sequence_hint`
- `dependency_reference_ids`
- role/type fields from shared model docs
- `source_instrument_id` and `target_instrument_id` where applicable

### 5.3 Idempotency/replay keys

- Parent replay identity: `(source_system, parent_event_reference, portfolio_id)`
- Child replay identity: `(parent_event_reference, child_transaction_reference)`
- Cash-leg identity: `(parent_event_reference, cash_leg_reference)` or deterministic link to `CASH_IN_LIEU` child

## 6. Processing Pipeline

### 6.1 Dependency-ready execution order

1. Parent event registered and validated.
2. Validate required child set for event category.
3. Process required `*_OUT` source children.
4. Process required `*_IN` target children.
5. Validate basis conservation and generate/verify synthetic flows for both product legs.
6. Process lot continuity output and held-since policy result.
7. Process `CASH_IN_LIEU` product leg (when present).
8. Process linked `ADJUSTMENT` cash leg.
9. Process optional `FEE` / `TAX` / `CHARGE` / classification children.
10. Reconcile event completion rules and emit final status.

### 6.2 Completion gates

Event is `COMPLETED` only when:

- required source and target legs succeed
- source quantities and basis transfer constraints satisfied
- synthetic flow invariants are satisfied for all required product legs
- lot mapping output persisted per policy
- optional overlays either completed or explicitly waived under policy

## 7. Required Validation and Reconciliation

- missing parent event -> hard fail
- required source leg missing -> hard fail
- required target leg missing -> hard fail
- dependency graph invalid -> hard fail
- insufficient source position -> hard fail
- synthetic flows missing/invalid sign/date/quantity/valuation -> hard fail
- cash-in-lieu mismatch between product and cash legs -> hard fail or park by policy
- synthetic flow/cash overlap detected -> park or hard fail based on policy
- reconciliation tolerance check:
  - source basis out = target basis in + fractional basis allocation + documented adjustment delta

## 8. Implementation Slices

### Slice 0 — Spec + model hardening
- lock transaction enums, role values, and linkage fields
- update schema and migration for CA parent+linkage fields
- extend synthetic flow DTO fields for source of flow and MVT attribution

### Slice 1 — Ingestion/API conformance
- extend transaction ingestion DTO validation:
  - require CA parent linkage for `CA` families
  - accept `CASH_IN_LIEU` and `ADJUSTMENT` pairing
- add OpenAPI/contract examples for full replacement bundle

### Slice 2 — Orchestrator and services
- implement dependency graph for CA parent/child
- enforce sequencing and completion rules
- emit deterministic child execution plan and replay status

### Slice 3 — Calculators
- position calculator: consume only position synthetic flows for performance/contribution
- cashflow calculator: consume `ADJUSTMENT` only for liquidity side
- ensure `POSITION_TRANSFER_*` and `POSITION_CASH_IN_LIEU_OUT` classification is isolated from funding flow classes

### Slice 4 — Persistence and auditability
- persist synthetic flow payloads and lot mapping metadata
- store link artifacts:
  - source->target mapping
  - cash-in-lieu fractional quantities
  - basis reconciliation summary
- expose CA view for diagnostics and replay support

### Slice 5 — Regression and conformance
- add unit/integration/e2e tests for:
  - full replacement without cash leg
  - mandatory exchange with external cash settlement
  - basis mismatch park/hard-fail behavior
  - duplicate replay idempotency
  - synthetic flow exclusion from portfolio flow metrics

### Slice 6 — Observability and rollout
- add event-level observability:
  - synthetic flow generation outcome
  - reconciliation status
  - linkage failures / park reasons
- execute full PR pipeline gate
- produce conformance report and close-loop review

## 9. Test Strategy

- Unit:
  - service validators for dependency and linkage
  - synthetic flow math helper functions
- Integration:
  - orchestrator + calculators with out-of-order child arrival
  - `CASH_IN_LIEU`+`ADJUSTMENT` pair processing
- End-to-end:
  - realistic full replacement bundle ingest
  - output correctness across position and portfolio calculators
- Negative:
  - synthetic-cash overlap injection
  - missing price/FX behavior by policy
  - source residual basis violations

## 10. Migration and Backward Compatibility

- Existing non-CA transaction behavior remains unchanged.
- Non-full replacement CA handling should be additive and guarded by `processing_category`.
- Feature-flag gating for strict reconciliation and hard-fail escalation is mandatory during rollout.

## 11. Open Items for Approval

- Confirm whether residual source basis policy default remains `false` for all tenants.
- Confirm FX behavior for synthetic flow base conversion in mixed-currency events:
  - upstream-provided only
  - derived via configured FX source
  - hard-fail vs park policy for missing FX
- Confirm exact `SyntheticFlowSource` enum value contract expected by downstream analytics.

## 12. References

- `docs/rfc-transaction-specs/transactions/CA/RFC-CA-FULL-REPLACEMENT-01.md`
- `docs/rfc-transaction-specs/shared/14-corporate-action-processing-model.md`
- `docs/rfc-transaction-specs/shared/15-corporate-action-child-transaction-role-and-typing-model.md`
- `docs/rfc-transaction-specs/shared/16-position-level-synthetic-flows-for-corporate-actions.md`
- `docs/rfc-transaction-specs/shared/07-accounting-cash-and-linkage.md`
