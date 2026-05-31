# CR-665: Pipeline Stage Latest Control Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`OperationsRepository.get_latest_financial_reconciliation_control_stage(...)` filters
`pipeline_stage_state` by `portfolio_id` and the fixed `FINANCIAL_RECONCILIATION` stage, then
orders by `business_date DESC`, `epoch DESC`, and `id DESC` to find the latest control-stage state.

The existing portfolio/status support index is aligned to status-filtered portfolio control-stage
lists, but it does not match this latest-stage lookup because the latest-stage query does not filter
by `status`.

## Change

Added `ix_pipeline_stage_state_port_stage_date_epoch_id` on:

1. `portfolio_id`
2. `stage_name`
3. `business_date DESC`
4. `epoch DESC`
5. `id DESC`

The index matches the repository predicate prefix and latest-control ordering.

## Impact

This narrows latest financial-reconciliation control-stage reads used by portfolio support
readiness and operational evidence views. It does not change route shape, response contracts,
database columns, wiki source, or platform contracts.

## Validation

Local validation passed:

1. focused database-model metadata proof
2. focused operations repository query-shape proof
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `python scripts/test_manifest.py --suite unit-db --quiet`
8. `git diff --check`
