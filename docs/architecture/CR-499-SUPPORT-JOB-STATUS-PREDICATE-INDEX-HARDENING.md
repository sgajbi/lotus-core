# CR-499: Support Job Status Predicate Index Hardening

Date: 2026-05-28

## Scope

Operations/support API query predicates for valuation, aggregation, and reprocessing job tables.

## Finding

The operations service normalizes incoming support-job status filters before calling the repository,
and the job tables store governed uppercase status values. The repository still wrapped stored status
columns in `upper(trim(...))` in several `WHERE` predicates.

That defensive SQL shape preserved tolerance for dirty stored values, but it also hid direct status
columns from existing composite indexes such as:

1. `ix_portfolio_valuation_jobs_portfolio_status_date_updated_id`
2. `ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id`
3. `ix_reprocessing_jobs_job_type_status_created_at_id`

This affected high-volume operations pages and calculation supportability views where banks need
predictable latency while monitoring valuation, aggregation, and replay backlogs.

## Change

Added an explicit repository helper that normalizes caller-provided status filters once, then compares
against the stored status column directly. Applied it to:

1. valuation job count and list filters,
2. aggregation job count and list filters,
3. reprocessing job count and list filters,
4. completed-valuation handoff checks,
5. superseded-valuation actionable-job checks.

Kept normalized status expressions for selected response labels and priority `CASE` expressions,
where they do not determine the indexable access path.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

Results:

1. Operations repository query-shape proof: `67 passed`
2. Touched-surface ruff: passed
3. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, database migration, wiki source, or platform contract change was required. The
support-job APIs now use index-friendly status predicates while preserving normalized API response
semantics.
