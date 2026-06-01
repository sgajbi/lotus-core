# CR-666: Reconciliation Latest Run Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`OperationsRepository.get_latest_reconciliation_run_for_portfolio_day(...)` filters
`financial_reconciliation_runs` by `portfolio_id`, `business_date`, and `epoch`, then orders by
control priority, `started_at DESC`, and `id DESC` to locate the latest reconciliation run for a
portfolio control day.

Existing reconciliation run indexes covered status-list, type-list, correlation, requester, unique
run-id, and dedupe-key paths, but not the portfolio/date/epoch latest-run support lookup.

## Change

Added `ix_fin_recon_runs_port_date_epoch_started_id` on:

1. `portfolio_id`
2. `business_date`
3. `epoch`
4. `started_at DESC`
5. `id DESC`

The index matches the repository predicate prefix and latest-run ordering suffix.

## Impact

This narrows latest reconciliation-run reads used by portfolio readiness, support overview, and
financial-control evidence paths. It does not change route shape, response contracts, database
columns, wiki source, or platform contracts.

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
