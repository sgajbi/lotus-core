# RFC 032 - Query Consistency and Race Condition Hardening

| Metadata | Value |
| --- | --- |
| Status | Implemented |
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

Request-scoped snapshot semantics are now enforced for analytics timeseries pagination paths:
1. Snapshot epoch is captured on first page and propagated via signed page token.
2. Subsequent pages must reuse the same epoch and scope fingerprint.
3. Scope mismatch is rejected deterministically as `INVALID_REQUEST`.
Classification: `Fully implemented and aligned` for RFC-032 scope.

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

Evidence:
- `src/services/query_service/app/repositories/position_repository.py`
- `src/services/query_service/app/repositories/analytics_timeseries_repository.py`
- `tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`
- `src/services/query_service/app/services/analytics_timeseries_service.py`
- `tests/unit/services/query_service/services/test_analytics_timeseries_service.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Business-date-based latest snapshot selection | Implemented | `position_repository.py`; unit repo tests |
| Epoch derived from timeseries for analytics paths | Implemented in analytics timeseries query patterns | `analytics_timeseries_repository.py` |
| Request-scoped snapshot semantics | Implemented for analytics timeseries page flows through tokenized `snapshot_epoch` + scope fingerprint enforcement | `analytics_timeseries_service.py`; service unit tests |
| Deterministic concurrent replay consistency tests | Implemented as drift-focused regression asserting token epoch reuse even if repository current epoch advances | `test_analytics_timeseries_service.py::test_position_timeseries_reuses_token_snapshot_epoch_under_concurrent_drift` |

## Design Reasoning and Trade-offs

1. Ranking by date/id directly addresses stale selection from out-of-order inserts.
2. Timeseries-derived epoch selection reduces dependency on potentially drifting state-table reads for analytics queries.

Trade-off:
- Snapshot consistency is now deterministic for tokenized timeseries workflows, while non-paginated single-shot reads remain governed by their as-of query semantics.

## Gap Assessment

No blocking correctness gaps remain under RFC-032 scope.

## Deviations and Evolution Since Original RFC

1. Some consistency improvements have landed in repository query primitives.
2. Next-phase contractual semantics and SLA behavior definitions are still pending.

## Proposed Changes

1. Keep monitoring for high-contention incident evidence that would justify heavier integration-level concurrency chaos testing.

## Test and Validation Evidence

1. Position repository query-shape regression tests:
   - `tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`
2. Analytics timeseries deterministic ranking implementation:
   - `src/services/query_service/app/repositories/analytics_timeseries_repository.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Query selection correctness hardening is implemented.
2. Request-scoped epoch consistency and drift regression checks are implemented.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should `as_of_epoch` be optionally exposed at API level for explicit client observability beyond signed token propagation?

## Next Actions

1. Maintain regression tests and observability around pagination token validation failures.
