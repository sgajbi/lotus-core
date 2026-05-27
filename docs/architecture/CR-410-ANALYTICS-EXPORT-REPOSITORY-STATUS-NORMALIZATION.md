# CR-410: Analytics Export Repository Status Normalization

Date: 2026-05-28

## Scope

Query-service operations repository analytics export job health, filtering, and priority ordering.

## Finding

CR-408 normalized analytics export lifecycle decisions at the service layer, but repository health
summary, count/list filters, and priority ordering still compared persisted `analytics_export_jobs`
status values directly. If persisted lifecycle values carried casing or whitespace drift, operations
counts could understate accepted/running/failed jobs, list filters could miss rows, and priority
ordering could push failed or stale jobs behind lower-urgency work.

## Change

Added a repository-level analytics export status expression using `lower(trim(status))`. Reused it
for analytics export health summary aggregation, status count/list filters, and priority ordering.
Updated query-shape tests to lock the normalized predicates and ordering contract.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations repository reliability slice that keeps export supportability counts, filters, and
operator ordering stable when persisted status control codes drift.
