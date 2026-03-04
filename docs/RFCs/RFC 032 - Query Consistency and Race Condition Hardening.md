# RFC 032 - Query Consistency and Race Condition Hardening

- Date: 2026-02-23
- Services Affected: `query-service`
- Status: Partially Implemented

## Summary

This RFC defines consistency hardening for read paths under concurrent reprocessing and ingestion.

## Findings

1. Latest position snapshot selection previously used `max(id)` and could return stale business dates.
2. Portfolio performance retrieval previously derived epoch from `position_state`, which can drift from `portfolio_timeseries` during in-flight recomputation.
3. Multi-query read workflows (`review`, `summary`, `positions_analytics`) still risk non-repeatable reads under concurrent writes.

## Implemented Now

1. Position snapshot selection changed to business-date ordering (`date desc, id desc`) per security.
2. Portfolio performance epoch now derives from `portfolio_timeseries` itself.
3. Added regression test for out-of-order ID inserts in `test_query_position_repository.py`.

## Next Phase

1. Introduce request-scoped snapshot semantics for query workflows:
   - transaction isolation strategy for read endpoints
   - explicit `as_of_epoch`/`as_of_date` contracts
2. Add consistency tests that simulate concurrent replay with deterministic expected outputs.
3. Define SLA-grade behaviors for partial/stale data exposure in API responses.
