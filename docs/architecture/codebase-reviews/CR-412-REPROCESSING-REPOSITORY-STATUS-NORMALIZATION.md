# CR-412: Reprocessing Repository Status Normalization

Date: 2026-05-28

## Scope

Query-service operations repository reprocessing status handling for lineage keys,
reprocessing keys, and reprocessing jobs.

## Finding

Reprocessing supportability had service-level normalization for caller filters and response
classification, but repository predicates still compared persisted `PositionState.status` and
`ReprocessingJob.status` values directly. Casing or whitespace drift could understate active or
stale reprocessing counts, miss lineage and reprocessing key filters, and mis-prioritize active or
stale remediation work in operator lists.

## Change

Added a repository-level reprocessing status expression using `upper(trim(status))`. Reused it for
reprocessing health aggregation, lineage status filtering and priority ordering, reprocessing key
count/list filters and priority ordering, and reprocessing job count/list filters. Lineage latest
valuation-job status now uses the existing support-job status expression before artifact-gap
classification. Updated operations repository query-shape tests to lock normalized predicates and
ordering behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations repository reliability slice that keeps reprocessing supportability counts, filters,
and operator ordering stable when persisted status control codes drift.
