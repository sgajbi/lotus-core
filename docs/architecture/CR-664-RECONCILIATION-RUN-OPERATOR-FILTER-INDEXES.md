# CR-664: Reconciliation Run Operator Filter Indexes

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The reconciliation run support-list repository accepts `correlation_id` and `requested_by`
operator filters and orders rows by control priority, `started_at DESC`, and row identity. The
model already covered portfolio/status and portfolio/reconciliation-type support reads, but the
operator investigation filters did not have matching composite indexes.

This left correlation-based and requester-based reconciliation support lookups dependent on less
selective portfolio or single-column indexes before applying the operator filter.

## Change

Added two PostgreSQL-safe model and migration indexes on `financial_reconciliation_runs`:

1. `ix_fin_recon_runs_port_corr_started_id`
2. `ix_fin_recon_runs_port_req_by_started_id`

Both indexes start with `portfolio_id`, include the operator filter column, and preserve the
support-list `started_at DESC, id ASC` ordering suffix used by the query-service repository.

## Impact

This narrows reconciliation control support reads during production incidents, replay triage, and
operator evidence review without changing route shape, response contracts, table columns, wiki
source, or platform contracts.

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
