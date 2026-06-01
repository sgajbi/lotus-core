# CR-512: Pipeline Stage Support Index Hardening

Date: 2026-05-29

## Scope

Query-service operations support reads for portfolio control stage state.

## Finding

Portfolio control stage support queries filter by `portfolio_id`, optional `status`, optional
business date/stage, and then list operationally important stage rows by priority, business date,
epoch, update time, and id. The table had a broad `(portfolio_id, business_date, stage_name,
status)` index, but no status-led support index for operator workflows that ask "show me failed or
replay-required stages for this portfolio".

The status filter also wrapped stored status values in `upper(trim(...))`, even though stage state
persists governed uppercase status values.

## Change

1. Added `ix_pipeline_stage_state_port_status_date_stage_epoch_updated_id` on
   `(portfolio_id, status, business_date DESC, stage_name, epoch DESC, updated_at DESC, id ASC)`.
2. Added Alembic migration `c0e7f8a9b0c1_perf_add_pipeline_stage_support_index.py` to normalize
   existing stage statuses and create the support index.
3. Changed portfolio-control stage status predicates and priority classification to use stored
   governed status values directly.
4. Added model metadata and repository query-shape proof for the new index-aligned predicate.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e7f8a9b0c1_perf_add_pipeline_stage_support_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e7f8a9b0c1_perf_add_pipeline_stage_support_index.py`
7. `git diff --check`

Results:

1. Focused model and operations repository proof: `76 passed`
2. Broader model and query-service repository proof: `218 passed`
3. Alembic head proof: `c0e7f8a9b0c1 (head)`
4. Migration contract smoke: passed
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is an index and
storage-contract hardening change for existing operations support endpoints.
