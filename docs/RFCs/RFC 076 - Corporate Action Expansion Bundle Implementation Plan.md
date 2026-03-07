# RFC 076 - Corporate Action Expansion Bundle Implementation Plan

**Status**: Implemented  
**Date**: 2026-03-07  
**Owner**: *TBD*  
**Reviewers**: *TBD*  
**Approvers**: *TBD*

## 0. Implementation Status Snapshot

- Bundle A (RFC-077) is completed.
- Bundle B completed under RFC-078.
- Bundle D baseline completed under RFC-079.
- Bundle C completed under RFC-080.
- RFC-076 execution plan is now fully delivered.

## 1. Purpose

Define the implementation bundling strategy for newly added CA transaction specifications so delivery is fast, deterministic, and aligned to the shared CA standards without creating orchestration or accounting debt.

This RFC covers:

- `RFC-CA-PARTIAL-TRANSFER-01`
- `RFC-CA-MULTI-TARGET-01`
- `RFC-CA-MIXED-CONSIDERATION-01`
- `RFC-CA-SPLIT-FAMILY-01`
- `RFC-CA-BONUS-STOCK-DIVIDEND-01`
- `RFC-CA-RIGHTS-ISSUE-FAMILY-01`
- `RFC-CA-REVERSAL-01`

## 2. Bundling Decision

### 2.1 Bundle A (implement together first): Transfer Expansion Bundle

- `RFC-CA-PARTIAL-TRANSFER-01`
- `RFC-CA-MULTI-TARGET-01`
- `RFC-CA-MIXED-CONSIDERATION-01`

Why these belong together:

- Same dependency graph model as RFC-075 (parent-child orchestration, source/target legs, basis transfer, overlays).
- Same synthetic-flow treatment (`POSITION_TRANSFER_OUT/IN`) with the same isolation contract from portfolio-level cashflow.
- Same cash overlay mechanics (`CASH_IN_LIEU`, `CASH_CONSIDERATION`, `ADJUSTMENT`) and linkage invariants.
- High reusable core: target-leg indexing, allocation groups, multi-target reconciliation, cash marker + settlement pairing.

### 2.2 Bundle B (implement together second): Same-Instrument Action Bundle

- `RFC-CA-SPLIT-FAMILY-01`
- `RFC-CA-BONUS-STOCK-DIVIDEND-01`

Why these belong together:

- Same-instrument quantity restatement family.
- No mandatory transfer-style synthetic out/in flow generation for main action.
- Shared lot-preservation and per-unit basis restatement pattern.
- Shared fractional handling (`CASH_IN_LIEU` + `ADJUSTMENT`) with similar rounding policies.

### 2.3 Bundle C (implement as dedicated stream): Rights Issue Family

- `RFC-CA-RIGHTS-ISSUE-FAMILY-01`

Why separate:

- Multi-stage lifecycle (allocate/elect/subscribe/sell/lapse/refund) is materially different from transfer/same-line CA flows.
- Introduces rights instrument lifecycle and election outcome semantics that are not reused by other bundles.
- Highest orchestration complexity and operational risk; should be built after Bundle A/B reusable CA kernel is stable.

### 2.4 Bundle D (cross-cutting): Reversal/Correction/Rebook

- `RFC-CA-REVERSAL-01`

Why cross-cutting:

- Applies to all CA categories.
- Must be built on top of stable category baselines (075 + Bundle A + Bundle B first).
- Requires deterministic reverse-order orchestration and read-model restatement guarantees across every supported CA family.

## 3. Target Execution Order

1. RFC-075 baseline completion/hardening (full replacement transfer).  
2. Bundle A (`PARTIAL_TRANSFER + MULTI_TARGET + MIXED_CONSIDERATION`).  
3. Bundle B (`SPLIT_FAMILY + BONUS_STOCK_DIVIDEND`).  
4. Bundle D foundation for already-implemented categories (`REVERSAL` for 075 + Bundle A + Bundle B).  
5. Bundle C (`RIGHTS_ISSUE_FAMILY`).  
6. Extend Bundle D to include rights lifecycle reversals.

## 4. Shared Reusable Components (must be carved out once)

The following must be reusable modules, not duplicated in per-RFC branches:

- CA parent-child dependency resolver with deterministic ordering policy.
- CA child linkage validator (`parent_event_reference`, dependency refs, source/target references, allocation groups).
- Synthetic-flow helper for transfer families (`MVT_PRICE_X_QTY`, classification mapping, FX conversion contract).
- Cash overlay linker for `CASH_IN_LIEU` / `CASH_CONSIDERATION` to `ADJUSTMENT`.
- Basis reconciliation engine:
  - source retained formula
  - source extinguished formula
  - multi-target allocation reconciliation
- CA status machine (`PENDING_*`, `PARTIALLY_APPLIED`, `PARKED`, `FAILED`, `COMPLETED`, and reversal statuses).
- CA observability contract (error reason taxonomy, reconciliation status, dependency blockage diagnostics).

## 5. Implementation Slices

### Slice 0: Contract and schema extension

- Extend transaction enums for all Bundle A/B/C types.
- Add any missing CA parent/child linkage and allocation fields needed by new specs.
- Add cashflow rules for new types and verify position/portfolio flow flags.

### Slice 1: Ingestion and canonical validation

- Add canonical validation for each bundle by category:
  - transfer bundles: source/target + overlays
  - same-instrument bundles: ratio/quantity restatement + overlays
  - rights bundle: lifecycle-stage and linkage integrity
- Add strict reason-code taxonomy for DLQ and park decisions.

### Slice 2: Orchestration engine hardening

- Deterministic execution for one-source-many-target with `target_leg_index`.
- Enforce dependency-safe completion gates by category.
- Add parking for incomplete child sets and missing required overlays.

### Slice 3: Calculator alignment

- Position calculator: category-specific quantity and basis semantics.
- Cashflow calculator:
  - transfer families: synthetic and real cash separation.
  - same-instrument families: no transfer synthetic out/in default for main action.
  - rights families: lifecycle cash/position classification consistency.
- Query/timeseries services: ensure classification flags produce expected position vs portfolio analytics.

### Slice 4: Reversal framework

- Introduce generic reverse-order reversal executor and reconciliation.
- Apply first to 075 + Bundle A/B categories.
- Add restatement visibility and event-chain lineage in query surfaces.

### Slice 5: Regression and CI gates

- Unit and integration suites by bundle + cross-bundle invariants.
- End-to-end suites for:
  - partial transfer multi-target
  - mixed consideration with cash boot + cash-in-lieu
  - split/bonus with fractional handling
  - cancel/correct/rebook of representative events
- CI manifest updates so each bundle has explicit contract suites.

## 6. Why not all-in-one single pass

Implementing all seven specs in one pass is possible but high-risk for hidden coupling:

- rights lifecycle introduces fundamentally different state transitions than transfer/same-line families.
- reversal requires stable forward semantics to avoid reversing undefined behavior.
- separating into the above bundles preserves velocity while reducing rollback and reconciliation risk.

## 7. Completion Record

Implemented RFCs for this expansion plan:

- RFC-077: Bundle A implementation plan.
- RFC-078: Bundle B implementation plan.
- RFC-079: Reversal framework implementation plan.
- RFC-080: Rights issue family implementation plan.

The RFC-076 bundle strategy and execution order are now closed as implemented.
