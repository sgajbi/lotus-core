# CR-414: Valuation Handoff Status Normalization

Date: 2026-05-28

## Scope

Query-service operations repository load-run progress handoff-latency query.

## Finding

The load-run progress repository path already normalized valuation and aggregation job statuses for
open-job counts, failed-job counts, and backlog age. The valuation-to-position-timeseries handoff
latency query still compared persisted `PortfolioValuationJob.status` directly to `COMPLETE`.
Casing or whitespace drift could exclude genuinely completed valuation jobs from latency samples
and waiting-count diagnostics, understating handoff pressure in banking-day load evidence.

## Change

Reused the repository-level support-job status expression for the valuation handoff query's
completed-status predicate. Updated the load-run progress query-shape test to lock the normalized
`upper(trim(portfolio_valuation_jobs.status)) = 'COMPLETE'` predicate.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations repository reliability slice that keeps load-run progress handoff evidence stable when
persisted valuation completion status control codes drift.
