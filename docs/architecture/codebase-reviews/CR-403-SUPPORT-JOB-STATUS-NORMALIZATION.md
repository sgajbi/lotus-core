# CR-403: Support Job Status Normalization

Date: 2026-05-28

## Scope

Query-service operations support-job retry, stale, and operational-state classification.

## Finding

Support-job state predicates compared raw uppercase status values. Padded valid values such as
` processing `, ` pending `, ` failed `, or ` skipped_no_position ` could therefore miss retry,
stale, failed, pending, processing, or skipped branches and be classified incorrectly in operations
supportability surfaces.

## Change

Added a query-service support-job status normalizer and used it before retry, stale, and
operational-state predicates. Updated direct coverage proving padded lower-case support-job status
values still classify into the correct operational states and retry/stale branches.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an operations
supportability classification and stale-job reliability slice.
