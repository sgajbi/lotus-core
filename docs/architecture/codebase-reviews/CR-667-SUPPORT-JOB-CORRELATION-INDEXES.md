# CR-667: Support Job Correlation Indexes

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Valuation and aggregation support-list repositories accept `correlation_id` filters for production
incident triage and replay tracing. The existing hot-path indexes cover portfolio/status/date and
claim ordering, but they do not provide a selective correlation lookup for support requests scoped
to one portfolio.

Because `correlation_id` is sparse, a full-table composite index would add avoidable write and
storage overhead.

## Change

Added partial PostgreSQL indexes for non-null correlation IDs:

1. `ix_val_jobs_port_corr_date_updated_id`
2. `ix_agg_jobs_port_corr_date_updated_id`

Both indexes start with `portfolio_id`, include `correlation_id`, and then retain the date,
`updated_at`, and `id` ordering columns used by the support job list surfaces.

## Impact

This narrows valuation and aggregation job support reads for correlation-based trace investigations
without changing route shape, response contracts, database columns, wiki source, or platform
contracts.

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
