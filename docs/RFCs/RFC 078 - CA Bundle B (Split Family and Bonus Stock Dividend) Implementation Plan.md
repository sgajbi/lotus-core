# RFC 078 - CA Bundle B (Split Family and Bonus Stock Dividend) Implementation Plan

**Status**: Implemented  
**Date**: 2026-03-07  
**Owner**: *TBD*  
**Reviewers**: *TBD*  
**Approvers**: *TBD*  

## 0. Implementation Status Snapshot

- Bundle B delivery is implemented in `lotus-core`.
- Same-instrument CA transaction families are supported with deterministic quantity direction and basis-preserving default semantics.
- Cashflow rule coverage, calculator behavior, and regression evidence are in place.

## 1. Purpose

Implement RFC-076 Bundle B according to:

- `docs/rfc-transaction-specs/transactions/CA/RFC-CA-SPLIT-FAMILY-01.md`
- `docs/rfc-transaction-specs/transactions/CA/RFC-CA-BONUS-STOCK-DIVIDEND-01.md`

while preserving core platform invariants:

- canonical transaction vocabulary (no aliases)
- deterministic processing
- isolated position-level flow treatment
- no hidden portfolio-funding side effects

## 2. Scope

### 2.1 In scope

- Canonical transaction types:
  - `SPLIT`, `REVERSE_SPLIT`, `CONSOLIDATION`
  - `BONUS_ISSUE`, `STOCK_DIVIDEND`
- Cost-calculator mapping for same-instrument quantity restatements.
- Position and query calculators for consistent quantity effect classification.
- Cashflow transfer direction support and rule seeding for Bundle B types.
- Test coverage for contract behavior across engine and service boundaries.

### 2.2 Out of scope

- Jurisdiction-specific accounting overrides beyond platform baseline.
- Advanced lot-level redistribution engines not present in current cost kernel.
- Event-level cancellation/correction orchestration (handled in RFC-079 baseline).

## 3. Canonical Behavior

### 3.1 Quantity treatment

- `SPLIT`, `BONUS_ISSUE`, `STOCK_DIVIDEND` are quantity-increase events.
- `REVERSE_SPLIT`, `CONSOLIDATION` are quantity-decrease events.

### 3.2 Basis treatment

- Bundle B action types use basis-preserving default:
  - `net_cost = 0`
  - `net_cost_local = 0`
  - no implicit realized P&L creation

### 3.3 Cashflow and classification

- Bundle B legs remain position-level transfer-classified flows for analytics consistency.
- Transfer-sign logic is explicit by type and not inferred only from `_IN`/`_OUT` suffix.

## 4. Architecture and Component Changes

### 4.1 Financial engine

- Added Bundle B types to `TransactionType`.
- Introduced `QuantityRestatementStrategy` and mapped Bundle B types.

### 4.2 Position calculator

- Added same-instrument restatement handling path for Bundle B.
- Enforced quantity-only transformation with basis unchanged.

### 4.3 Cashflow calculator

- Expanded transfer-sign maps to include Bundle B types.
- Prevented mis-signing from suffix-only fallback logic.

### 4.4 Query services

- Extended position flow effect type sets for Bundle B directionality.

### 4.5 Database/migration

- Seeded `cashflow_rules` entries for Bundle B via:
  - `alembic/versions/d8e9f0a1b2c3_feat_add_ca_expansion_cashflow_rules.py`

## 5. Implementation Slices

### Slice B0 - Contract and Type Extension

- Enum extension and canonical type acceptance across core pipeline.

### Slice B1 - Calculator Semantics

- Strategy mapping and basis-preservation implementation.
- Position and query quantity impact alignment.

### Slice B2 - Cashflow Rule Alignment

- Added bundle-specific transfer rules with deterministic timing/classification defaults.

### Slice B3 - Regression Hardening

- Added/extended targeted tests in cost, position, cashflow, and query domains.

## 6. Validation and Test Matrix

- Cost invariants:
  - Bundle B restatement types preserve total basis.
- Position invariants:
  - quantity adjusted in correct direction by type.
- Cashflow invariants:
  - transfer sign deterministic for Bundle B transaction types.
- Query invariants:
  - position flow quantity effect matches calculator directionality.

Executed suites include:

- targeted unit suites for modified files
- `make test-transaction-portfolio-flow-bundle-contract`
- `make lint`
- `make typecheck`

## 7. Acceptance Criteria

- No unknown-type errors for Bundle B transactions in core calculators.
- Quantity direction and basis semantics match Bundle B canonical defaults.
- Cashflow sign/classification is deterministic and test-covered.
- RFC documentation and index reflect implemented status and evidence.

## 8. Evidence

- `src/services/calculators/cost_calculator_service/app/cost_engine/domain/enums/transaction_type.py`
- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`
- `src/services/query_service/app/services/position_flow_effects.py`
- `alembic/versions/d8e9f0a1b2c3_feat_add_ca_expansion_cashflow_rules.py`
- `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
- `tests/unit/services/query_service/services/test_position_flow_effects.py`

## 9. Current Status

- Implemented and aligned.

## 10. Failure Semantics and Error Handling

- Unknown Bundle B type: hard validation failure in cost engine (`Unknown transaction type`).
- Invalid sign/classification behavior: blocked by deterministic transfer-sign mapping and regression tests.
- Basis drift risk for same-instrument actions: mitigated by explicit `QuantityRestatementStrategy` with zero-cost outputs.

## 11. Observability and Operational Diagnostics

- Existing calculator logs/metrics remain authoritative for:
  - transaction processing success/failure
  - cashflow creation outcomes
  - deterministic ordering paths
- Bundle B behavior is observable through transaction type and calculated output fields in persisted transaction/cashflow records.

## 12. Rollout and Rollback

### 12.1 Rollout

1. Apply Alembic migrations to head.
2. Deploy calculator/query services with updated type/strategy mappings.
3. Validate with contract suites and targeted Bundle B scenarios.

### 12.2 Rollback

- Code rollback: revert deployment to prior release image.
- Schema rollback: execute migration downgrade for Bundle B/C rules if needed.
- Data consistency note: already-processed events remain audit-traceable and should be reprocessed under established replay controls if rollback spans processing windows.

## 13. Risks and Mitigations

- Risk: downstream consumers assume `_IN/_OUT` suffix only.
  - Mitigation: explicit transfer-sign map for non-suffix Bundle B types.
- Risk: hidden basis drift from default strategies.
  - Mitigation: dedicated restatement strategy with zero-cost invariants.
- Risk: documentation-code drift.
  - Mitigation: RFC index evidence links updated in same change set.

## 14. Conformance Statement

RFC-078 is implemented to the current `lotus-core` baseline with deterministic behavior, migration coverage, and regression evidence aligned to RFC-076 bundle governance.
