# RFC 061 - SELL Transaction RFC Implementation Plan

| Field | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-03-01 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/SELL/RFC-SELL-01.md`; shared transaction lifecycle and modeling specs |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; transaction precision and durability standards |
| Scope | In repo |

## Executive Summary
RFC 061 defines incremental SELL canonicalization using the BUY delivery pattern. Repository evidence shows SELL slices `0..6` were delivered with conformance artifacts, dedicated test suite wiring, and query/observability surfaces.

The RFC content still reads partly as a forward-looking plan, so this standardized version re-baselines it as an implementation record with explicit residual enhancements.

## Original Requested Requirements (Preserved)
1. Deliver SELL in controlled slices (0 to 6).
2. Add explicit SELL validation taxonomy and deterministic failure semantics.
3. Enforce disposal semantics, oversell policy controls, and linkage consistency.
4. Persist policy metadata and transaction linkage fields.
5. Provide query surfaces for disposal/audit/reconciliation.
6. Publish conformance evidence and CI regression gate (`transaction-sell-contract`).

## Current Implementation Reality
1. SELL slice artifacts exist under transaction-spec paths.
2. SELL linkage/policy metadata and validation tests exist.
3. SELL query surfaces exist in query-service (`sell_state` routes and tests).
4. CI includes `transaction-sell-contract` test suite in matrix.
5. As with BUY, lifecycle telemetry is strong, while centralized persisted lifecycle state-machine depth remains a follow-on improvement area.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Slice artifact trail (0..6) | Implemented | `docs/rfc-transaction-specs/transactions/SELL/SELL-SLICE-0-GAP-ASSESSMENT.md` .. `SELL-SLICE-6-CONFORMANCE-REPORT.md` |
| SELL validation + reason codes | Implemented | `tests/unit/libs/portfolio_common/test_sell_validation.py`; slice-1 artifact |
| Linkage and policy metadata persistence | Implemented | `tests/unit/libs/portfolio_common/test_sell_linkage.py`; slice-2 artifact |
| Calculation and invariants | Implemented | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`; slice-3 artifact |
| Disposal/cash-linkage behavior | Implemented | slice-4 artifact; calculator/query tests |
| Query + observability completion | Implemented | `tests/integration/services/query_service/test_sell_state_router.py`; slice-5 artifact |
| CI conformance gate | Implemented | `scripts/test_manifest.py` (`transaction-sell-contract`); `.github/workflows/ci.yml` |

## Design Reasoning and Trade-offs
1. Slice-by-slice rollout minimized accounting regression risk.
2. Reuse of shared transaction-domain foundations across BUY/SELL improved consistency.
3. Trade-off: some deep observability-state persistence concerns remain outside initial SELL baseline scope.

## Gap Assessment
1. RFC status and narrative still mix "implemented" and "plan" language.
2. Persisted lifecycle-state framework standardization across transaction types should be elevated as follow-on governance work.

## Deviations and Evolution Since Original RFC
1. RFC was drafted as an implementation plan and then executed rapidly.
2. Current document required normalization to distinguish completed work vs residual enhancements.

## Proposed Changes
1. Keep RFC 061 as the historical SELL implementation plan and execution record.
2. Track remaining cross-transaction lifecycle observability depth as a follow-on delta.

## Test and Validation Evidence
1. `docs/rfc-transaction-specs/transactions/SELL/SELL-SLICE-6-CONFORMANCE-REPORT.md`
2. `tests/unit/libs/portfolio_common/test_sell_validation.py`
3. `tests/unit/libs/portfolio_common/test_sell_linkage.py`
4. `tests/integration/services/query_service/test_sell_state_router.py`
5. `scripts/test_manifest.py` and `.github/workflows/ci.yml` (`transaction-sell-contract`)

## Original Acceptance Criteria Alignment
1. Slice execution and evidence trail: aligned.
2. SELL canonicalization and validation coverage: aligned.
3. Disposal/query/observability baseline: aligned.
4. Advanced cross-transaction lifecycle-state persistence: partially aligned (follow-on).

## Rollout and Backward Compatibility
1. SELL capabilities were delivered incrementally and test-gated.
2. Existing transaction workflows were preserved while canonical SELL behavior was hardened.

## Open Questions
1. Should lifecycle-state persistence be standardized as a shared transaction framework requirement across BUY/SELL and successor RFCs?

## Next Actions
1. Rebaseline this RFC text as implemented record language in future minor update.
2. Carry forward lifecycle-state persistence enhancements in transaction governance backlog.
