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
  - position-history replay ordering
  - cost-basis transaction ordering
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
- The same service-owned dependency model is enforced in position replay and cost-basis ordering.

## 4. Architecture and Component Changes

### 4.1 Ordering domain policy

- Corporate-action classification and ordering are owned in:
  - `portfolio_transaction_processing_service/app/domain/transaction/corporate_action/`

### 4.2 Engine sorter alignment

- Cost and position ordering consume the owner policy from:
  - `app/domain/cost_basis/calculation/transaction_ordering.py`
  - `app/domain/position/history.py`

### 4.3 Regression

- Added tests for rights lifecycle deterministic ordering in:
  - corporate-action ordering tests
  - cost sorter and position-history tests

## 5. Implementation Slices

### Slice D0 - Dependency Model Extension

- Rights lifecycle rank definitions added to the transaction-processing domain policy.

### Slice D1 - Cross-Component Consistency

- Cost and position replay ordering consume the same owned policy.

### Slice D2 - Determinism Proof

- Added tests covering lifecycle ordering assertions in both paths.

## 6. Validation and Test Matrix

- Deterministic ordering tests:
  - rights lifecycle ordering in `corporate_action_dependency_rank`
  - rights lifecycle ordering in `CostTransactionSorter`
  - linked-leg ordering in position history
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

- `src/services/portfolio_transaction_processing_service/app/domain/transaction/corporate_action/ordering.py`
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/corporate_action/classification.py`
- `src/services/portfolio_transaction_processing_service/app/domain/cost_basis/calculation/transaction_ordering.py`
- `src/services/portfolio_transaction_processing_service/app/domain/position/history.py`
- `tests/unit/services/portfolio_transaction_processing_service/transaction/test_corporate_action_ordering.py`
- `tests/unit/services/portfolio_transaction_processing_service/cost/test_sorter.py`

## 9. Current Status

- Implemented and aligned as reversal-ready dependency-ordering baseline.

## 10. Failure Semantics and Error Handling

- Missing lifecycle rank coverage for supported rights types: treated as ordering defect and must fail regression gates.
- Ordering divergence between replay and sorter: treated as high-severity correctness issue and blocked by dual-path tests.
- Non-canonical type input: fails existing transaction-type validation paths.

## 11. Observability and Operational Diagnostics

- Deterministic ordering can be verified from:
  - position-history replay records and ordering tests
  - sorted transaction processing order in engine logs and test traces
- The ordering model remains centralized in the transaction-processing domain for diagnostics and
  future extension.

## 12. Rollout and Rollback

### 12.1 Rollout

1. Deploy the unified transaction-processing image containing ordering policy and consumers.
2. Validate with rights lifecycle ordering regression tests.
3. Confirm no ordering regressions for Bundle A baseline scenarios.

### 12.2 Rollback

- Revert the transaction-processing ordering slice atomically to the previous release.
- Re-run replay determinism verification on rollback target before production promotion.

## 13. Risks and Mitigations

- Risk: future CA types added in one ordering path but not the other.
  - Mitigation: keep ordering changes coupled and covered by parity tests.
- Risk: reversal extensions built on inconsistent forward ordering.
  - Mitigation: treat this RFC as mandatory prerequisite gate for reversal rollout.

## 14. Conformance Statement

RFC-079 baseline requirements are implemented for deterministic lifecycle dependency ordering and reversal-ready replay consistency in the current `lotus-core` architecture.
