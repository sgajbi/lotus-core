# RFC 033 - Support and Lineage API Surface

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-05 |
| Owners | `query-service` operations support surface |
| Depends On | RFC 057, API-first operations governance |
| Scope | Support and lineage APIs replacing direct DB troubleshooting dependence |

## Executive Summary

RFC 033 established API-first operational diagnostics in query-service.
Phase 1 endpoints are implemented and test-covered:
1. `/support/portfolios/{portfolio_id}/overview`
2. `/lineage/portfolios/{portfolio_id}/securities/{security_id}`

Implementation has already expanded with additional support/lineage endpoints (`valuation-jobs`, `aggregation-jobs`, `lineage keys`).
But Phase 2 items (correlation trace APIs, DLQ/replay history APIs, authz policy integration) remain open.

Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC 033 requested:
1. Support overview API for operational state.
2. Lineage API for per-key epoch/watermark and latest artifact markers.
3. OpenAPI-quality docs for new operational surfaces.
4. Phase 2 additions: correlation trace, DLQ/replay observability, access policy hardening.

## Current Implementation Reality

Implemented:
1. Support overview endpoint and service/repository aggregation logic.
2. Lineage endpoint for portfolio-security keys.
3. Additional operational endpoints (`valuation-jobs`, `aggregation-jobs`, `lineage keys`) beyond initial phase 1 summary.
4. OpenAPI tests and router dependency tests validate behavior and error mappings.

Not yet implemented in query-service surface:
1. Correlation-id trace API across outbox/consumer lifecycle.
2. Role-based access policy tied to future authn/authz stream.

Implemented via ingestion-service operational surface (not query-service route family):
1. DLQ state and replay-audit APIs were delivered under ingestion operations contracts.

Evidence:
- `src/services/query_service/app/routers/operations.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `tests/integration/services/query_service/test_operations_router_dependency.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_service/test_main_app.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Support overview API | Implemented | operations router/service/repo |
| Lineage API for one key | Implemented | operations router/service/repo |
| OpenAPI quality on support endpoints | Implemented with explicit summaries/descriptions + tests | routers + integration tests |
| Correlation trace API | Not implemented | endpoint inventory |
| DLQ/replay support API | Implemented in ingestion-service operations surface; not exposed as query-service route family | `src/services/event_replay_service/app/routers/ingestion_operations.py`; `RFC-DELTA-BACKLOG` (`RFC-033-D02`) |
| Role-based policy integration | Pending broader authn/authz RFC stream | governance dependency |

## Design Reasoning and Trade-offs

1. API-first support surfaces reduce operational DB dependency and standardize diagnostics.
2. Adding list endpoints (jobs/lineage keys) improved triage workflows beyond minimum phase 1.

Trade-off:
- Without correlation/DLQ trace endpoints, deep incident forensics still require stitching from multiple tools/logs.

## Gap Assessment

Remaining deltas:
1. Add correlation trace API with deterministic event lineage timeline (or formally keep deferred).
2. Integrate access policy controls once authn/authz baseline is available.

## Deviations and Evolution Since Original RFC

1. Implementation exceeded initial phase-1 endpoint count.
2. Phase-2 forensic and policy capabilities remain intentionally deferred.

## Proposed Changes

1. Keep classification as `Partially implemented (requires enhancement)`.
2. Treat query-service DLQ/replay endpoint expansion as optional unless ingestion-service APIs prove insufficient.

## Test and Validation Evidence

1. Router dependency integration tests:
   - `tests/integration/services/query_service/test_operations_router_dependency.py`
2. Service-level unit tests:
   - `tests/unit/services/query_service/services/test_operations_service.py`
3. OpenAPI contract checks:
   - `tests/integration/services/query_service/test_main_app.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Core phase-1 support/lineage functionality is in place.
2. Remaining phase-2 objectives are still pending.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should correlation trace API be implemented in query-service directly or surfaced via dedicated operations service aggregator across repositories?

## Next Actions

1. Track phase-2 support/lineage deltas in backlog (`RFC-033-D01` deferred, `RFC-033-D02` done).
2. Align rollout with authn/authz RFC for access controls.
