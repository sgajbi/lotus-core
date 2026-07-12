# CR-408: Analytics Export Lifecycle Status Normalization

Date: 2026-05-28

## Scope

Query-service analytics timeseries export job lifecycle decisions in
`AnalyticsTimeseriesService`.

## Finding

The operations supportability surface already normalized analytics export statuses, but the
analytics export service still used raw string comparisons for completion, in-flight reuse, result
availability, and result retrieval. Padded or case-varied persisted values such as ` Completed ` or
` RUNNING ` could therefore make completed exports look unavailable, prevent idempotent completed
job reuse, or reject available export payloads.

## Change

Added a service-local analytics export lifecycle status normalizer and routed response
availability, idempotent reuse classification, stale in-flight detection, JSON result retrieval,
and NDJSON result retrieval through it. Responses now expose the canonical lifecycle status when a
persisted value can be normalized. Updated analytics-timeseries service tests to prove padded
completed and running states still produce correct reuse, result-availability, and download
behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/analytics_timeseries_service.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
analytics export lifecycle reliability slice that keeps idempotent job reuse and export download
gates stable when persisted control-code casing or whitespace drifts.
