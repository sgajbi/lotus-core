# RFC 059 - BUY Transaction RFC Implementation Plan

| Field | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-27 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/BUY/RFC-BUY-01.md`; shared transaction lifecycle specs |
| Related Standards | RFC-0067 API governance; durability/consistency and rounding standards |
| Scope | In repo |

## Executive Summary
RFC 059 provided a slice-by-slice implementation plan for BUY canonicalization. Implementation evidence shows all slices were executed with artifacts, tests, query surfaces, and CI suite wiring. Residual gaps documented in the slice-6 conformance report remain accepted but non-blocking.

The RFC should now be treated as a delivery record with follow-on enhancements, not a purely proposed plan.

## Original Requested Requirements (Preserved)
1. Deliver BUY behavior through incremental slices (0..6).
2. Add canonical BUY modeling and validation reason codes.
3. Persist linkage and policy metadata (`economic_event_id`, `linked_transaction_group_id`, policy id/version).
4. Harden calculation invariants and explicit BUY semantics (including realized P&L zero behavior).
5. Add durable BUY lot/accrued-offset/cash-linkage behavior.
6. Expose query and observability surfaces for BUY lifecycle supportability.
7. Provide conformance evidence and dedicated regression gate.

## Current Implementation Reality
1. BUY validation/model and metadata propagation tests are implemented.
2. BUY lot/accrued-offset persistence and query APIs are implemented.
3. BUY state query routes are available under query-service (`lots`, `accrued-offsets`, `cash-linkage`).
4. Slice artifacts and conformance report exist under `docs/rfc-transaction-specs/transactions/BUY/`.
5. Conformance report records accepted residual gaps: no single persisted lifecycle state-machine record and limited timing-policy expansion.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Slice artifact trail | Implemented | `docs/rfc-transaction-specs/transactions/BUY/BUY-SLICE-0-GAP-ASSESSMENT.md` .. `BUY-SLICE-6-CONFORMANCE-REPORT.md` |
| Canonical BUY validation + reason codes | Implemented | `tests/unit/libs/portfolio_common/test_buy_validation.py`; slice-1 artifact |
| Metadata persistence/linkage | Implemented | `tests/unit/libs/portfolio_common/test_transaction_metadata_contract.py`; calculator/persistence tests |
| Calculation invariants and BUY semantics | Implemented | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`; slice-3 artifact |
| Lot and accrued-offset durability | Implemented | `src/services/calculators/cost_calculator_service/app/repository.py`; `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py` |
| Query/read-model and supportability | Implemented | `src/services/query_service/app/routers/buy_state.py`; `tests/integration/services/query_service/test_buy_state_router.py` |
| Dedicated conformance gate | Implemented with accepted residuals | `docs/rfc-transaction-specs/transactions/BUY/BUY-SLICE-6-CONFORMANCE-REPORT.md`; `scripts/test_manifest.py` (`transaction-buy-contract`) |

## Design Reasoning and Trade-offs
1. Slice-first rollout reduced regression risk in core transaction pipelines.
2. Reusing shared domain components in `portfolio_common` improved reuse for SELL and future transaction RFCs.
3. Some diagnostics capabilities were deferred to avoid overloading BUY baseline delivery.

## Gap Assessment
1. Persisted lifecycle stage-machine record per transaction is not yet implemented.
2. Extended timing policy programmability is partial.
3. RFC references to artifact paths should point to actual `docs/rfc-transaction-specs/transactions/BUY/` locations.

## Deviations and Evolution Since Original RFC
1. RFC text still reads as "Proposed" while implementation evidence shows completed delivery slices.
2. Artifact location in plan text drifted from actual repository layout.

## Proposed Changes
1. Rebaseline RFC 059 from "proposed plan" to "implemented plan record with residual enhancements".
2. Correct artifact references to canonical BUY transaction-spec path.
3. Keep accepted residuals as explicit follow-up deltas rather than reopening completed slices.

## Test and Validation Evidence
1. `tests/unit/transaction_specs/test_buy_slice0_characterization.py`
2. `tests/unit/libs/portfolio_common/test_buy_validation.py`
3. `tests/unit/libs/portfolio_common/test_transaction_metadata_contract.py`
4. `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py`
5. `tests/integration/services/query_service/test_buy_state_router.py`
6. `docs/rfc-transaction-specs/transactions/BUY/BUY-SLICE-6-CONFORMANCE-REPORT.md`

## Original Acceptance Criteria Alignment
1. Slice execution and traceability: aligned.
2. Canonical BUY model/validation behaviors: aligned.
3. Lot/offset/cash-linkage and query visibility: aligned.
4. Full lifecycle-state persistence and extended timing policy: partially aligned (accepted residual).

## Rollout and Backward Compatibility
1. BUY enhancements were delivered incrementally, reducing break risk.
2. Existing transaction ingestion/query pathways remained available during migration.

## Open Questions
1. Should lifecycle stage persistence become a mandatory cross-transaction framework requirement (BUY/SELL/DIVIDEND) in a new RFC?
2. Should timing policy catalogs be centralized before wider transaction-type rollout?

## Next Actions
1. Correct RFC references and status language to match implemented state.
2. Track lifecycle-state persistence and timing policy expansion as follow-on enhancement deltas.
