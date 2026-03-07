# RFC 077 - CA Bundle A (Partial Transfer Multi-Target Mixed Consideration) Implementation Plan

**Status**: In Progress  
**Date**: 2026-03-07  
**Owner**: *TBD*  
**Reviewers**: *TBD*  
**Approvers**: *TBD*

## 1. Purpose

Define and execute the first implementation bundle from RFC-076:

- `RFC-CA-PARTIAL-TRANSFER-01`
- `RFC-CA-MULTI-TARGET-01`
- `RFC-CA-MIXED-CONSIDERATION-01`

This bundle extends RFC-075 with source-retained transfer behavior, multi-target determinism, and mixed stock+cash overlays.

## 2. Scope

### 2.1 In scope (Bundle A)

- CA transaction typing support:
  - `SPIN_OFF`, `SPIN_IN`
  - `DEMERGER_OUT`, `DEMERGER_IN`
  - `CASH_CONSIDERATION`
- Position/cost/cashflow baseline semantics for these types.
- Cashflow rule seeding and transfer sign handling.
- Basis-only source-retained transfer handling (`quantity = 0` with basis transfer-out).

### 2.2 Deferred to later slices

- Full CA parent-child orchestrator with dependency graph execution.
- Multi-target allocation group reconciliation engine.
- Category-complete completion gates and parking taxonomy.
- Advanced mixed-consideration realized P&L decomposition policies.

## 3. Slice Plan

### Slice A0 (implemented in this change set)

- Extend engine enum and calculator mappings for Bundle A types.
- Add CA bundle A cashflow rules migration.
- Add source-retained basis-only transfer semantics in cost and position calculators.
- Extend query position-flow effect mapping for Bundle A types.
- Add regression tests for:
  - position effects
  - cost calculation basis-only transfer behavior
  - query quantity effect mapping

### Slice A1 (implemented in this change set)

- Ingestion/canonical validation reason-code coverage for Bundle A types.
- Strict linkage checks for mixed consideration (`CASH_CONSIDERATION` marker to `ADJUSTMENT`).

### Slice A2 (implemented in this change set)

- Parent-child dependency orchestration for one-source-many-target processing.
- Deterministic target leg ordering (`target_leg_index` fallback rules).

### Slice A3

- Allocation-group reconciliation and multi-target basis conservation checks.
- Observability and replay diagnostics for bundle-specific failure modes.

## 4. Design Decisions

- `SPIN_OFF` / `DEMERGER_OUT` are treated as source-retained transfer-out legs.
- Basis-only transfer-out is explicitly supported:
  - quantity can remain unchanged
  - cost basis is reduced deterministically via `net_cost` (or `gross_transaction_amount` fallback).
- `CASH_CONSIDERATION` is introduced as a product/event marker type and is not auto-mapped to portfolio cash movement; real cash remains `ADJUSTMENT`.

## 5. Acceptance Criteria

- Bundle A transaction types are accepted by core enum and calculator pipelines.
- No unknown-type failures for new Bundle A types in cost engine.
- Position and query quantity effects are deterministic for new types.
- Migration contract checks pass with new bundle migration.
- Unit suites covering touched domains remain green.

## 6. Current Status

- Slice A0: **Completed** (code + tests + migration added)
- Slice A1: **Completed** (Bundle A validation module + consumer guardrails + tests)
- Slice A2: **Completed** (deterministic Bundle A dependency/target ordering in replay + engine sort)
- Slice A3+: Pending
