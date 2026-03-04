# RFC 064 - Benchmark Exposure History and Position Timeseries Contract for lotus-risk Historical Attribution

| Field | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-03-01 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core + lotus-risk integration owners |
| Depends On | RFC 062, RFC 063 |
| Related Standards | RFC-0067 API vocabulary and contract governance |
| Scope | Cross-repo |

## Executive Summary
RFC 064 extends historical attribution readiness for lotus-risk by combining portfolio position timeseries with benchmark exposure history.

Current lotus-core implementation covers reusable prerequisites (position timeseries + enrichment), but the proposed benchmark exposure endpoint family is not implemented. This RFC is therefore partially implemented and remains an active enhancement track.

## Original Requested Requirements (Preserved)
1. Reuse position timeseries exposure contract for portfolio exposures.
2. Add benchmark exposure history endpoint:
   - `POST /integration/benchmarks/{benchmark_id}/analytics/exposure-timeseries`
3. Align taxonomy/dimension semantics between portfolio and benchmark exposure contracts.
4. Keep deterministic pagination and canonical field naming for attribution pipelines.

## Current Implementation Reality
1. Position timeseries contracts required by RFC 064 are implemented in analytics-input router.
2. Instrument enrichment contract exists and is reusable for issuer-level grouping.
3. Benchmark exposure-timeseries endpoint proposed by RFC 064 is not present in query-service routes.
4. No dedicated tests found for the missing benchmark exposure endpoint contract.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Portfolio position timeseries exposure input | Implemented | `src/services/query_service/app/routers/analytics_inputs.py`; `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py` |
| Instrument enrichment reuse | Implemented | `src/services/query_service/app/routers/integration.py` (`/integration/instruments/enrichment-bulk`) |
| Benchmark exposure-timeseries endpoint | Not implemented | no route match in `src/services/query_service/app/routers`; RFC text only |
| Deterministic pagination for benchmark exposure family | Not implemented (endpoint missing) | no endpoint/service/test artifacts |

## Design Reasoning and Trade-offs
1. Reusing RFC-063 position timeseries avoids duplicate exposure contracts for portfolio-side inputs.
2. Missing benchmark exposure history keeps active-risk attribution dependent on external stitching/workarounds.
3. Implementing this endpoint in lotus-core can preserve canonical benchmark exposure semantics without pushing raw-reference stitching complexity downstream.

## Gap Assessment
1. The key RFC-064 delta is unimplemented: benchmark exposure-timeseries contract.
2. This is still relevant under current architecture because active-risk workflows need aligned portfolio-vs-benchmark exposure histories.

## Deviations and Evolution Since Original RFC
1. The RFC was implementation-ready, but only the reusable prerequisite contracts landed.
2. Final active-risk benchmark exposure contract remains open.

## Proposed Changes
1. Implement `benchmark exposure-timeseries` under `/integration/benchmarks/{benchmark_id}/analytics/exposure-timeseries`.
2. Reuse RFC-062 benchmark composition/reference semantics and RFC-063 pagination/lineage envelope patterns.
3. Add contract and integration tests covering dimension alignment and pagination determinism.

## Test and Validation Evidence
1. `src/services/query_service/app/routers/analytics_inputs.py`
2. `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py`
3. `src/services/query_service/app/routers/integration.py`

## Original Acceptance Criteria Alignment
1. Total-risk attribution input reuse via position-timeseries: aligned.
2. Active-risk benchmark exposure contract enablement: not aligned (missing endpoint).

## Rollout and Backward Compatibility
1. New benchmark exposure endpoint can be added additively with no breaking change.
2. Downstream consumers can migrate from custom stitching to canonical benchmark exposure contract when available.

## Open Questions
1. Should benchmark exposure rows use constituent `security_id` only, or support synthetic benchmark constituent keys when vendor identifiers are absent?
2. Should first implementation support `daily` only, with explicit forward path for wider frequencies?

## Next Actions
1. Implement and test benchmark exposure-timeseries endpoint as RFC-064-D01.
2. Add cross-repo consumer validation with lotus-risk historical attribution pipelines.
