# CR-411: Support Job Repository Status Normalization

Date: 2026-05-28

## Scope

Query-service operations repository valuation and aggregation support-job status handling.

## Finding

Valuation and aggregation job supportability had service-level normalization for caller filters and
response classifiers, but repository predicates still compared persisted support-job statuses
directly. Casing or whitespace drift in `portfolio_valuation_jobs.status` or
`portfolio_aggregation_jobs.status` could distort backlog counts, failed-job counts, stale-job
classification, filtered job lists, and operator priority ordering. Superseded-pending valuation
job exclusion also treated padded pending statuses as non-pending.

## Change

Added a repository-level support-job status expression using `upper(trim(status))`. Reused it for
valuation and aggregation health summaries, list/count status filters, support-job priority
ordering, and actionable valuation pending-job exclusion. Updated operations repository query-shape
tests to lock the normalized predicates and ordering behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations repository reliability slice that keeps supportability counts, filters, and operator
ordering stable when persisted valuation or aggregation job status control codes drift.
