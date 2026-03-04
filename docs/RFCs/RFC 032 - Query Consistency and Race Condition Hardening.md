# RFC 032 - Query Consistency and Race Condition Hardening

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-05 |
| Owners | `query-service` |
| Depends On | RFC 057 (query contract consolidation) |
| Scope | Deterministic read selection and concurrency consistency safeguards |

## Executive Summary

RFC 032 addresses correctness risks in query reads under concurrent ingestion/reprocessing.
Current implementation delivered core fixes:
1. Latest snapshot selection uses business date ordering (not `max(id)`).
2. Performance/timeseries epoch selection derives from timeseries records.
3. Regression tests cover ranking and epoch-consistency query construction.

However, full request-scoped snapshot semantics and concurrent replay consistency harnesses remain future scope.
Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC 032 requested:
1. Fix stale snapshot selection by ordering on business date.
2. Avoid epoch drift by deriving from timeseries sources for performance reads.
3. Harden multi-query read workflows against non-repeatable reads under concurrent writes.
4. Add deterministic concurrency tests and define API stale/partial-data behavior.

## Current Implementation Reality

Implemented:
1. Position repository ranks latest snapshots by `date desc, id desc` per security.
2. As-of query variants and ranked snapshot/history fallbacks exist.
3. Analytics timeseries repository uses row-number partitioning with epoch ordering from timeseries tables.
4. Unit tests assert query generation uses the corrected ordering.

Not yet fully implemented:
1. No explicit repo-wide request-scoped snapshot transaction model documented/enforced across all multi-query workflows.
2. No dedicated concurrent replay simulation suite proving repeatable consistency contracts end-to-end.

Evidence:
- `src/services/query_service/app/repositories/position_repository.py`
- `src/services/query_service/app/repositories/analytics_timeseries_repository.py`
- `tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`
- `src/services/query_service/app/services/analytics_timeseries_service.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Business-date-based latest snapshot selection | Implemented | `position_repository.py`; unit repo tests |
| Epoch derived from timeseries for analytics paths | Implemented in analytics timeseries query patterns | `analytics_timeseries_repository.py` |
| Request-scoped snapshot semantics | Not fully implemented | service/repository design review |
| Deterministic concurrent replay consistency tests | Not fully implemented | test inventory review |

## Design Reasoning and Trade-offs

1. Ranking by date/id directly addresses stale selection from out-of-order inserts.
2. Timeseries-derived epoch selection reduces dependency on potentially drifting state-table reads for analytics queries.

Trade-off:
- Without full request-scoped snapshot semantics, consistency across multi-query composition endpoints can still vary under heavy concurrent writes.

## Gap Assessment

Remaining high-value gaps:
1. Introduce explicit as-of snapshot contract for composite read endpoints.
2. Add deterministic concurrency test harness for replay/ingestion overlap scenarios.

## Deviations and Evolution Since Original RFC

1. Some consistency improvements have landed in repository query primitives.
2. Next-phase contractual semantics and SLA behavior definitions are still pending.

## Proposed Changes

1. Keep classification as `Partially implemented (requires enhancement)`.
2. Continue with explicit phase-2 consistency contract work and stress tests.

## Test and Validation Evidence

1. Position repository query-shape regression tests:
   - `tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`
2. Analytics timeseries deterministic ranking implementation:
   - `src/services/query_service/app/repositories/analytics_timeseries_repository.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Core query correctness hardening implemented.
2. Full request-scoped consistency model and concurrency proof suite remain open.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should request-scoped consistency be enforced via DB transaction isolation, explicit `as_of_epoch` API contract, or both?

## Next Actions

1. Track remaining request-scoped consistency work and concurrency test harness in delta backlog.
2. Define explicit stale/partial data response behavior for composite query endpoints.
3. Keep status as `Partially Implemented` until `RFC-032-D01` is closed in `RFC-DELTA-BACKLOG`.
