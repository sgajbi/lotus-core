# RFC 080 - CA Bundle C (Rights Issue Family) Implementation Plan

**Status**: Implemented  
**Date**: 2026-03-07  
**Owner**: *TBD*  
**Reviewers**: *TBD*  
**Approvers**: *TBD*  

## 0. Implementation Status Snapshot

- Bundle C rights issue family baseline is implemented in `lotus-core`.
- Canonical rights lifecycle types are supported across enum, calculators, cashflow rules, query flow effects, and deterministic ordering.
- Regression coverage is added for lifecycle directionality and ordering invariants.

## 1. Purpose

Implement RFC-076 Bundle C aligned with:

- `docs/rfc-transaction-specs/transactions/CA/RFC-CA-RIGHTS-ISSUE-FAMILY-01.md`

so rights lifecycle transactions are processed as first-class canonical transaction types with consistent analytics outcomes.

## 2. Scope

### 2.1 In scope

- Canonical rights lifecycle transaction types:
  - `RIGHTS_ANNOUNCE`
  - `RIGHTS_ALLOCATE`
  - `RIGHTS_EXPIRE`
  - `RIGHTS_ADJUSTMENT`
  - `RIGHTS_SELL`
  - `RIGHTS_SUBSCRIBE`
  - `RIGHTS_OVERSUBSCRIBE`
  - `RIGHTS_REFUND`
  - `RIGHTS_SHARE_DELIVERY`
- Cost-strategy mapping for rights inflow/outflow lifecycle legs.
- Position-calculator support for rights quantity transitions.
- Cashflow transfer-sign handling and rule seeding for rights types.
- Query position-flow effect alignment.
- Deterministic ordering support for rights lifecycle phases.

### 2.2 Out of scope

- Full election workflow/state orchestration service.
- Rights-specific policy overlays not part of baseline canonical behavior.

## 3. Canonical Behavior

### 3.1 Type semantics baseline

- Inflow rights legs:
  - `RIGHTS_ALLOCATE`, `RIGHTS_SHARE_DELIVERY`
- Outflow rights legs:
  - `RIGHTS_SUBSCRIBE`, `RIGHTS_OVERSUBSCRIBE`, `RIGHTS_SELL`, `RIGHTS_EXPIRE`
- Administrative marker/baseline:
  - `RIGHTS_ANNOUNCE`, `RIGHTS_ADJUSTMENT`
- Refund baseline:
  - `RIGHTS_REFUND` as transfer inflow classification baseline.

### 3.2 Cost semantics baseline

- Allocation/delivery map to inflow strategy.
- Subscribe/sell/expire/oversubscribe map to outflow strategy.
- Refund uses non-disposition baseline strategy.

### 3.3 Cashflow semantics baseline

- Rights types are seeded in `cashflow_rules`.
- Transfer sign logic is explicit by canonical type.

## 4. Architecture and Component Changes

### 4.1 Financial engine

- Extended `TransactionType` enum for all rights lifecycle types.
- Added strategy mapping in cost calculator for rights types.

### 4.2 Position calculator

- Added rights inflow/outflow types to transfer handling branch.

### 4.3 Cashflow calculator

- Extended transfer-sign mapping for rights lifecycle types.

### 4.4 Query services

- Extended `position_flow_effects` type sets for rights flows.

### 4.5 Ordering and replay

- Added rights lifecycle dependency ranks to shared ordering and sorter.

### 4.6 Migration

- Seeded rights cashflow rules via:
  - `alembic/versions/d8e9f0a1b2c3_feat_add_ca_expansion_cashflow_rules.py`

## 5. Implementation Slices

### Slice C0 - Contract and Type Model

- Added canonical rights types to engine enum.

### Slice C1 - Calculator Integration

- Cost, position, and query behavior aligned to rights lifecycle types.

### Slice C2 - Cashflow Rule and Directionality

- Added rights rule seeding and transfer sign handling.

### Slice C3 - Deterministic Lifecycle Ordering

- Added lifecycle precedence in ordering helpers and sorter.

### Slice C4 - Regression Hardening

- Added rights lifecycle tests across impacted modules.

## 6. Validation and Test Matrix

- Cost tests:
  - inflow vs outflow strategy mapping for rights lifecycle.
- Position tests:
  - quantity impacts for rights lifecycle types.
- Cashflow tests:
  - transfer sign correctness for rights types.
- Query tests:
  - position flow quantity effects for rights types.
- Ordering tests:
  - deterministic lifecycle ordering for rights stages.

Executed suites include:

- targeted unit suites for touched files
- `make test-transaction-portfolio-flow-bundle-contract`
- `make lint`
- `make typecheck`

## 7. Acceptance Criteria

- Rights lifecycle transaction types are accepted and processed end-to-end.
- Directionality is consistent across cost, position, cashflow, and query services.
- Lifecycle ordering is deterministic for replay and sorting.
- RFC and index artifacts reflect implementation evidence and closure.

## 8. Evidence

- `src/services/calculators/cost_calculator_service/app/cost_engine/domain/enums/transaction_type.py`
- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`
- `src/services/query_service/app/services/position_flow_effects.py`
- `src/libs/portfolio-common/portfolio_common/ca_bundle_a_ordering.py`
- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py`
- `alembic/versions/d8e9f0a1b2c3_feat_add_ca_expansion_cashflow_rules.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
- `tests/unit/services/query_service/services/test_position_flow_effects.py`
- `tests/unit/libs/portfolio-common/test_events.py`
- `tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py`

## 9. Current Status

- Implemented and aligned.

## 10. Failure Semantics and Error Handling

- Unknown rights transaction type: hard failure in transaction cost engine.
- Missing cashflow rule for rights type: treated as configuration error and routed to DLQ by cashflow consumer.
- Directional mismatch across calculators: prevented through explicit type-direction maps and regression assertions.

## 11. Observability and Operational Diagnostics

- Rights lifecycle processing is observable via:
  - transaction type lineage in persisted transaction records
  - cashflow classification/timing outputs
  - deterministic ordering assertions in replay/sorter tests
- Existing service metrics and logs remain authoritative for runtime behavior.

## 12. Rollout and Rollback

### 12.1 Rollout

1. Apply migration head including rights cashflow rules.
2. Deploy calculator/query services with rights type support.
3. Validate contract suites for rights directionality and ordering.

### 12.2 Rollback

- Revert service deployment as a unit across affected calculators and query services.
- Downgrade migration entries if rollback requires rule-level reversion.
- Use replay controls for deterministic restatement where rollback overlaps processed windows.

## 13. Risks and Mitigations

- Risk: rights lifecycle cash semantics vary across upstream systems.
  - Mitigation: canonical type handling is explicit and auditable; upstream mapping remains controlled at ingestion contracts.
- Risk: incremental additions introduce ordering or sign regressions.
  - Mitigation: lifecycle-order tests and transfer-sign tests are now mandatory regression guards.
- Risk: schema/rule drift across environments.
  - Mitigation: migration contract checks and explicit migration evidence in RFC/index.

## 14. Conformance Statement

RFC-080 rights lifecycle baseline is implemented end-to-end for canonical type support, calculator propagation, migration/rule coverage, and deterministic ordering aligned with RFC-076 governance.
