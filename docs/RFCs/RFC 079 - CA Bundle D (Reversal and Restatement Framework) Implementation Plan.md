# RFC 079 - CA Bundle D (Reversal and Restatement Framework) Implementation Plan

**Status**: Implemented  
**Date**: 2026-03-07  
**Owner**: *TBD*  
**Reviewers**: *TBD*  
**Approvers**: *TBD*  

## 0. Implementation Status Snapshot

- Bundle D baseline has been implemented for deterministic CA dependency ordering.
- Forward/replay ordering now supports rights lifecycle stages and aligns across services.
- This establishes the required foundation for safe cancel/correct/rebook extensions.

## 1. Purpose

Implement RFC-076 Bundle D baseline in alignment with:

- `docs/rfc-transaction-specs/transactions/CA/RFC-CA-REVERSAL-01.md`

with focus on deterministic ordering and replay safety prerequisites for reversal/restatement correctness.

## 2. Scope

### 2.1 In scope

- Deterministic dependency-rank extension for rights lifecycle legs.
- Ordering alignment between:
  - `portfolio_common.events.transaction_event_ordering_key`
  - financial engine sorter dependency rank
- Regression tests validating lifecycle order stability.

### 2.2 Out of scope

- Full reversal parent/child status machine persistence rollout.
- Dedicated reversal orchestration service and restatement mode APIs.

## 3. Canonical Behavior

### 3.1 Dependency precedence

- Rights lifecycle precedence is explicitly enforced:
  - announce/allocate
  - election legs (`subscribe`, `oversubscribe`, `sell`, `expire`, `adjustment`)
  - share delivery
  - refunds

### 3.2 Replay determinism

- Equal-date/equal-time event processing remains deterministic by standardized ordering keys.
- Same dependency model is enforced in both replay ordering and engine sort logic.

## 4. Architecture and Component Changes

### 4.1 Ordering library update

- Extended CA dependency ranking in:
  - `portfolio_common/ca_bundle_a_ordering.py`

### 4.2 Engine sorter alignment

- Mirrored dependency ranking in:
  - `cost_calculator_service/app/cost_engine/processing/sorter.py`

### 4.3 Regression

- Added tests for rights lifecycle deterministic ordering in:
  - events ordering tests
  - sorter tests

## 5. Implementation Slices

### Slice D0 - Dependency Model Extension

- Rights lifecycle rank definitions added to shared ordering logic.

### Slice D1 - Cross-Component Consistency

- Sorter ranking updated to match shared ordering model exactly.

### Slice D2 - Determinism Proof

- Added tests covering lifecycle ordering assertions in both paths.

## 6. Validation and Test Matrix

- Deterministic ordering tests:
  - rights lifecycle ordering in `transaction_event_ordering_key`
  - rights lifecycle ordering in `TransactionSorter`
- Non-regression:
  - existing Bundle A ordering tests remain green.

Executed suites include:

- targeted sorter/events tests
- `make lint`
- `make typecheck`

## 7. Acceptance Criteria

- Rights lifecycle events process in deterministic canonical order.
- Replay ordering and sorter ordering are aligned.
- Existing Bundle A deterministic behavior is unchanged.
- RFC references and evidence are updated in index/governance docs.

## 8. Evidence

- `src/libs/portfolio-common/portfolio_common/ca_bundle_a_ordering.py`
- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py`
- `tests/unit/libs/portfolio-common/test_events.py`
- `tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py`

## 9. Current Status

- Implemented and aligned as reversal-ready dependency-ordering baseline.

## 10. Failure Semantics and Error Handling

- Missing lifecycle rank coverage for supported rights types: treated as ordering defect and must fail regression gates.
- Ordering divergence between replay and sorter: treated as high-severity correctness issue and blocked by dual-path tests.
- Non-canonical type input: fails existing transaction-type validation paths.

## 11. Observability and Operational Diagnostics

- Deterministic ordering can be verified from:
  - replay sequence artifacts (`transaction_event_ordering_key`)
  - sorted transaction processing order in engine logs and test traces
- The ordering model remains centralized for easier diagnostics and future extension.

## 12. Rollout and Rollback

### 12.1 Rollout

1. Deploy shared ordering library and sorter updates together.
2. Validate with rights lifecycle ordering regression tests.
3. Confirm no ordering regressions for Bundle A baseline scenarios.

### 12.2 Rollback

- Revert sorter/ordering updates atomically to previous release.
- Re-run replay determinism verification on rollback target before production promotion.

## 13. Risks and Mitigations

- Risk: future CA types added in one ordering path but not the other.
  - Mitigation: keep ordering changes coupled and covered by parity tests.
- Risk: reversal extensions built on inconsistent forward ordering.
  - Mitigation: treat this RFC as mandatory prerequisite gate for reversal rollout.

## 14. Conformance Statement

RFC-079 baseline requirements are implemented for deterministic lifecycle dependency ordering and reversal-ready replay consistency in the current `lotus-core` architecture.
