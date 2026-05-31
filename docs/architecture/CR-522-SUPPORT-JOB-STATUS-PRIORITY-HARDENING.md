# CR-522: Support Job Status Priority Hardening

Date: 2026-05-31

## Scope

Query-service operations support reads for:

1. valuation jobs
2. aggregation jobs
3. reprocessing jobs

## Finding

Operations support count/list filters already normalize caller status values once and compare them
directly with governed stored job statuses. The priority and status-label helper still wrapped the
same job status columns in `upper(trim(...))`, leaving mixed predicate guidance in the same
repository and adding unnecessary expression work to support-list ordering for high-volume job
tables.

The job writers persist uppercase lifecycle statuses, and the tables already carry raw
status-oriented indexes. Historical rows needed a one-time normalization before the support
priority helper could safely use the stored values directly.

## Change

1. Added Alembic migration `c0f5a6b7c8d9_perf_normalize_support_job_statuses.py` to normalize
   valuation, aggregation, and reprocessing job statuses to uppercase trimmed values.
2. Changed `_support_job_status_expr(...)` to return the stored status column directly.
3. Updated query-shape proof for valuation, aggregation, and reprocessing job support lists so the
   priority CASE expressions no longer wrap status columns in `upper(trim(...))`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0f5a6b7c8d9_perf_normalize_support_job_statuses.py`
6. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0f5a6b7c8d9_perf_normalize_support_job_statuses.py`
7. `git diff --check`

Results:

1. Operations repository proof: `67 passed`
2. Alembic head proof: `c0f5a6b7c8d9 (head)`
3. Migration SQL smoke passed.
4. Unit-db migration apply suite: `9 passed`
5. Touched-surface ruff passed.
6. Touched-surface format check passed.
7. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is support-query
predicate cleanup for existing operations APIs and job lifecycle storage contracts.
