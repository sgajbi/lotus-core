# CR-633: Reprocessing Job Correlation Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The support reprocessing-job list/count queries can filter reset-watermark jobs by
`correlation_id`, `status`, job id, normalized security id, and portfolio-impact scope. The model
already declared partial reset-watermark support indexes for pending fan-out priority and
normalized security lookup, but correlation-scoped operator lookups still had to rely on broader
job-type/status indexes before applying the correlation filter.

## Change

Added the partial PostgreSQL index `ix_reproc_resetwm_corr_status_created_id` on
`reprocessing_jobs(correlation_id, status, created_at, id)` with
`job_type = 'RESET_WATERMARKS'`. The SQLAlchemy model metadata, Alembic migration, PostgreSQL
identifier guard coverage, wiki source, and review ledger now carry the same index truth.

## Impact

This tightens operational support reads for reprocessing-job correlation investigations without
changing API shape, query semantics, worker claim behavior, or replay contracts.

Wiki source changed in `wiki/Database-Migrations.md`; publication must wait until this branch is
merged to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
