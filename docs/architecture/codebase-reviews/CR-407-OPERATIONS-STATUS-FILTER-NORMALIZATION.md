# CR-407: Operations Status Filter Normalization

Date: 2026-05-28

## Scope

Query-service operations list filters for lineage keys, valuation jobs, aggregation jobs, analytics
export jobs, reconciliation runs, portfolio control stages, reprocessing keys, and reprocessing
jobs.

## Finding

Operations response classifiers normalized status values, but request-side status filters were
still forwarded raw into repository predicates. Padded or case-varied caller filters such as
` processing `, ` failed `, ` current `, or ` requires_replay ` could therefore miss rows even
though the same statuses were classified correctly after retrieval.

## Change

Added explicit support-status and analytics-export-status filter normalizers at the operations
service boundary. Repository calls now receive canonical uppercase support/control statuses and
canonical lowercase analytics-export statuses while returned records continue to preserve persisted
status values. Updated direct operations-service tests proving padded caller status filters are
normalized before repository lookup.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations supportability query-filter reliability slice.
