# RFC 074 - Portfolio-Level Flow Bundle Implementation Plan (FEE TAX DEPOSIT WITHDRAWAL TRANSFER_IN TRANSFER_OUT)

| Field | Value |
| --- | --- |
| Status | Approved (In Progress) |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/CHARGE/RFC-CHARGE-01.md`; `docs/rfc-transaction-specs/transactions/CASH MOVEMENT/RFC-CASH-MOVEMENT-01.md`; `docs/rfc-transaction-specs/transactions/TRANSFER_IN_OUT/RFC-TRANSFER-01.md`; shared transaction specs |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; shared transaction lifecycle standards; RFC-071 dual-leg ADJUSTMENT alignment |
| Scope | In repo |

## Executive Summary
This RFC defines a single bundled implementation pass for:
1. `FEE`
2. `TAX`
3. `DEPOSIT`
4. `WITHDRAWAL`
5. `TRANSFER_IN`
6. `TRANSFER_OUT`

These six transaction types have strong implementation synergy:
1. all are portfolio-level flow semantics in the target model;
2. none should use product-leg auto-generated `ADJUSTMENT` cash leg behavior;
3. all require shared validation, policy/timing, cashflow classification, and audit/linkage hardening;
4. all touch the same service boundaries (ingestion, persistence, cost/position/cashflow/timeseries, query, tests).

Decision:
1. implement as one coordinated iteration (single RFC and unified slice train);
2. still execute in internal slices for safety, testability, and rollback clarity.

## Response to Scope Question (Together vs Separate)
Recommended approach: implement together.

Reasoning:
1. shared primitives are the same across all six types (validation framework, policy metadata, timing semantics, replay/idempotency, query visibility);
2. calculator consistency requires a single cross-type pass to avoid temporary semantic drift;
3. classification correctness (`is_position_flow`, `is_portfolio_flow`, cashflow sign/timing) is most safely corrected in one harmonized update;
4. transfer and cash-movement semantics can reuse the same modular building blocks without type-by-type duplication.

Only reason to split:
1. if release-risk policy requires a staged rollout by type despite shared code path.

No hard technical blocker was identified that requires separation.

## Confirmed Direction
1. These transaction types are treated as portfolio-level flows.
2. `AUTO_GENERATE` mode is not required for these six transaction types.
3. Existing dual-leg ADJUSTMENT model from RFC-071 remains for position-level product transactions (BUY/SELL/DIVIDEND/INTEREST), not this bundle.
4. Reuse existing endpoints and contracts; no dedicated new endpoints.

## Current Baseline (Observed in Code)
1. Transaction enums already include these types in calculator engine.
2. Cashflow rules table has seeded rules for these types, but alignment is incomplete:
 - `TAX` is currently seeded with `is_portfolio_flow = false` (target is `true` for this RFC).
3. Position logic includes explicit branches:
 - `DEPOSIT`, `WITHDRAWAL`, `FEE`, `TAX`, `TRANSFER_IN`, `TRANSFER_OUT`.
 - current behavior is mixed and not yet normalized to canonical portfolio-level flow invariants.
4. Cost engine strategies currently treat these types via generic inflow/outflow defaults; canonical portfolio-level behavior is not fully codified.
5. No dedicated transaction-domain modules exist yet for this bundle equivalent to dividend/interest validation/linkage modules.

## Original Requested Requirements (Preserved)
1. Implement `FEE`, `TAX`, `DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, `TRANSFER_OUT` together in one iteration.
2. Enforce portfolio-level flow semantics for all six types.
3. Do not require `AUTO_GENERATE` cash-leg mode for these transaction types.
4. Ensure complete end-to-end propagation across:
 - database and migrations
 - ingestion and persistence
 - cost, position, cashflow, timeseries calculators
 - query and reporting contracts
 - unit/integration/e2e tests
 - documentation and conformance evidence

## Requirement-to-Implementation Gap Matrix
| Requirement | Current State | Gap | Planned Slice |
| --- | --- | --- | --- |
| Canonical bundled validation for all six types | Not implemented | No shared transaction-domain validation package for this bundle | Slice 1 |
| Portfolio-level flow flags aligned for all six | Partially implemented | `TAX` portfolio-flow seed mismatch; mixed downstream assumptions | Slice 2 |
| No-`AUTO_GENERATE` enforcement for bundle | Not implemented | No explicit bundle-level guardrail against auto-generate semantics | Slice 1-2 |
| Harmonized cost/position semantics | Partially implemented | Current strategy mix is generic and inconsistent with canonical target | Slice 3 |
| Cashflow sign/classification/timing consistency | Partially implemented | Rule and logic behavior is partially aligned but not canonicalized together | Slice 2-3 |
| Timeseries portfolio-flow propagation | Partially implemented | Depends on upstream cashflow classification correctness | Slice 3 |
| Query supportability with canonical fields | Partially implemented | Generic transaction views exist; bundle-specific clarity and tests are missing | Slice 4 |
| Dedicated regression suite and CI lane | Not implemented | No bundle contract suite for these six types together | Slice 5 |
| Full conformance closure report | Not implemented | No bundle-level RFC-to-evidence mapping artifact | Slice 6 |

## Slice Plan (Single Iteration, Internal Slices)

## Slice Execution Status
| Slice | Status | Evidence |
| --- | --- | --- |
| 0 | Completed | `PORTFOLIO-FLOW-BUNDLE-SLICE-0-GAP-ASSESSMENT.md`; characterization tests for position/cashflow baseline |
| 1 | Completed | `PORTFOLIO-FLOW-BUNDLE-SLICE-1-VALIDATION-GUARDRAILS.md`; shared guardrail helper + consumer enforcement + unit tests |
| 2 | Completed | `PORTFOLIO-FLOW-BUNDLE-SLICE-2-CLASSIFICATION-ALIGNMENT.md`; TAX rule migration + regression tests |
| 3 | Completed | `PORTFOLIO-FLOW-BUNDLE-SLICE-3-CALCULATOR-HARMONIZATION.md`; position-calculator semantic alignment + canonicalized bundle tests |
| 4 | Pending | Query/observability and contract hardening |
| 5 | Pending | Regression suite and CI wiring |
| 6 | Pending | Conformance report and closure |

### Slice 0 - Gap Assessment and Characterization Baseline
Deliverables:
1. `docs/rfc-transaction-specs/transactions/*/*-SLICE-0-GAP-ASSESSMENT.md` for this bundle scope.
2. Characterization tests locking current behavior before targeted refactor.
3. Explicit list of behavior that must change to reach canonical target.

Exit Criteria:
1. Baseline is reproducible and test-locked.
2. All semantic deltas are cataloged as intentional changes.

### Slice 1 - Shared Validation and No-AUTO_GENERATE Guardrails
Deliverables:
1. Shared transaction-domain models/reason-codes/validation for the six bundle types.
2. Explicit enforcement:
 - bundle transaction types do not depend on `cash_entry_mode = AUTO_GENERATE`
 - reject/flag invalid mode usage for these types.
3. Deterministic policy metadata defaults and validation outcomes.

Exit Criteria:
1. Canonical validation exists with deterministic reason codes.
2. No-auto-generate rule is tested and enforced.

### Slice 2 - Cashflow Rule and Classification Alignment
Deliverables:
1. Migration/seed alignment for `cashflow_rules`:
 - portfolio-level flow classification for all six types.
2. Rule-table and consumer logic consistency for classification/timing/sign.
3. Regression tests for rule loading, cache behavior, and sign outcomes.

Exit Criteria:
1. `is_portfolio_flow` and classification semantics are canonical and deterministic.
2. All six types are aligned in cashflow outputs and persisted fields.

### Slice 3 - Calculator and Timeseries Harmonization
Deliverables:
1. Cost/position logic harmonization for portfolio-level flow semantics.
2. Timeseries correctness checks for BOD/EOD portfolio cashflow behavior.
3. Deterministic handling for transfer/cash/charge direction in daily outputs.

Exit Criteria:
1. Cross-calculator semantics are consistent for all six types.
2. No double counting or sign drift across position/cashflow/timeseries.

### Slice 4 - Query and Observability Contract Hardening
Deliverables:
1. Extend existing transaction/cashflow query contracts where required.
2. Ensure OpenAPI descriptions/examples remain RFC-0067 compliant.
3. Add supportability diagnostics for policy/classification/linkage state.

Exit Criteria:
1. Operators and downstream services can explain behavior for all six types from existing endpoints.
2. No dedicated new endpoint family is introduced.

### Slice 5 - Regression Suite and CI Wiring
Deliverables:
1. Manifest suite entry:
 - `transaction-portfolio-flow-bundle-contract`
2. Makefile target:
 - `test-transaction-portfolio-flow-bundle-contract`
3. CI matrix wiring for the bundle suite.

Exit Criteria:
1. Bundle regression suite is CI-enforced.
2. Unit + integration coverage for six-type interactions is deterministic.

### Slice 6 - Conformance Report and Closure
Deliverables:
1. `.../PORTFOLIO-FLOW-BUNDLE-SLICE-6-CONFORMANCE-REPORT.md`.
2. Requirement-to-evidence mapping across code/tests/migrations/docs.
3. Residual risk list and accepted follow-on items.

Exit Criteria:
1. RFC sections mapped to shipped evidence.
2. Any residual gap is explicitly documented and approved.

## Test and Validation Strategy
Per approved slice, run:
1. `python -m ruff check ...`
2. `make typecheck`
3. targeted pytest suites for impacted modules
4. `python scripts/migration_contract_check.py --mode alembic-sql` (if schema or seed touched)
5. `python scripts/openapi_quality_gate.py` (if API touched)
6. `python scripts/api_vocabulary_inventory.py --validate-only` (if API touched)

Bundle acceptance run:
1. new bundle suite (unit + integration);
2. targeted e2e scenarios covering fee/tax/deposit/withdrawal/transfer combinations and timeseries outcomes.

## Architecture Guardrails
1. Modular and reusable components only:
 - shared validation package
 - shared classification/policy helpers
 - shared reconciliation assertions
2. No duplicated per-type logic where a common primitive fits.
3. Additive changes preferred over behavior rewrites.
4. Keep existing endpoint surfaces; evolve contracts in place.
5. Preserve RFC-071 boundary:
 - no ADJUSTMENT auto-generate workflow added to this bundle.

## Risks and Mitigations
1. Risk: transfer semantics (security vs cash) introduce ambiguity if forced into one shape.
 - Mitigation: keep transfer subtype policy explicit and test both asset flavors.
2. Risk: silent portfolio-flow misclassification in downstream analytics.
 - Mitigation: migration + calculator + timeseries assertions in one bundled pass.
3. Risk: regression from broad multi-type change.
 - Mitigation: strict slice gates, characterization tests, and CI bundle suite.

## Approval Gate (No Implementation Before Approval)
Implementation does not start until this RFC is approved.

Approval checklist:
1. bundled single-iteration scope accepted for all six types;
2. no-auto-generate direction accepted for this bundle;
3. portfolio-level flow classification direction accepted for all six types;
4. slice plan and validation gates accepted.
