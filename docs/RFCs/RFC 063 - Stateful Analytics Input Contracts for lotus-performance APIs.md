# RFC 063 - Stateful Analytics Input Contracts for lotus-performance APIs

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-01 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core integration query owners; lotus-performance consumers |
| Depends On | RFC 058, RFC 062, RFC-0067 |
| Related Standards | API vocabulary governance; rounding and precision standards |
| Scope | Cross-repo |

## Executive Summary
RFC 063 defines high-volume stateful analytics input contracts for lotus-performance. The core endpoint family is implemented: portfolio timeseries, position timeseries, analytics reference metadata, and async export job lifecycle endpoints.

The implemented shape aligns closely with the RFC goals, including deterministic paging, lineage metadata, and separation of enrichment responsibilities.

## Original Requested Requirements (Preserved)
1. Provide dedicated portfolio and position analytics timeseries input contracts.
2. Keep enrichment non-redundant (separate enrichment contract usage).
3. Add async export job contracts for large dataset retrieval.
4. Support deterministic paging/chunking and stream-friendly retrieval patterns.
5. Preserve strict ownership boundary (lotus-core inputs, lotus-performance analytics).

## Current Implementation Reality
1. `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` implemented.
2. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` implemented.
3. `POST /integration/portfolios/{portfolio_id}/analytics/reference` implemented.
4. Export job lifecycle endpoints (`create`, `status`, `result`) implemented.
5. Integration tests and router dependency tests validate request/response and export retrieval behavior.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Portfolio timeseries input endpoint | Implemented | `src/services/query_control_plane_service/app/routers/analytics_inputs.py`; `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py` |
| Position timeseries input endpoint | Implemented | same router/service path |
| Analytics reference metadata endpoint | Implemented | `analytics_inputs.py` |
| Async export create/status/result endpoints | Implemented | `analytics_inputs.py` (`/exports/analytics-timeseries/jobs*`) |
| Deterministic error mapping and contract behavior | Implemented | `analytics_inputs.py` + router dependency tests |
| Ownership separation and enrichment reuse model | Implemented in contract design | analytics router descriptions + enrichment endpoint retained in integration router |

## Design Reasoning and Trade-offs
1. Dedicated timeseries endpoints reduce overloading of snapshot endpoints for long-horizon analytics acquisition.
2. Async export contracts improve reliability for large extraction windows.
3. Keeping enrichment out of bulk timeseries rows avoids payload bloat and duplication.

## Gap Assessment
1. No major functional gap in core RFC-063 contract family identified.
2. Ongoing performance tuning and stream-format operational validation should continue as non-functional hardening.

## Deviations and Evolution Since Original RFC
1. RFC text is "proposed" language while major contract surfaces are implemented.
2. Implementation adds practical error and export lifecycle handling details consistent with production needs.

## Proposed Changes
1. Rebaseline RFC 063 status/narrative to implemented baseline.
2. Keep performance-scale hardening under RFC 065/066 operational gates.

## Test and Validation Evidence
1. `src/services/query_control_plane_service/app/routers/analytics_inputs.py`
2. `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py`
3. `src/services/query_service/app/services/analytics_timeseries_service.py`

## Original Acceptance Criteria Alignment
1. New timeseries contracts present and usable: aligned.
2. Async export lifecycle available: aligned.
3. Ownership and non-redundant enrichment model: aligned.

## Rollout and Backward Compatibility
1. Endpoints are additive in integration contract space.
2. Existing consumers can adopt incrementally per dataset/use case.

## Open Questions
1. Should explicit cross-consumer conformance suites be added for lotus-performance historical windows with large-page and ndjson result checks?

## Next Actions
1. Maintain analytics input contract and export job tests in CI.
2. Continue load-profile validation through RFC-066 gates for large-window requests.
