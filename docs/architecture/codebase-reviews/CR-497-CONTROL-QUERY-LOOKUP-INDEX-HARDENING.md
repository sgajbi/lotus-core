# CR-497: Control Query Lookup Index Hardening

Date: 2026-05-28

## Scope

Analytics export idempotency lookup and reconciliation finding support-summary lookup paths.

## Finding

`AnalyticsExportRepository.get_latest_by_fingerprint(...)` filters export jobs by
`dataset_type` and `request_fingerprint`, then selects the latest row by `id DESC`. The table had
separate indexes on those fields but no composite index matching the idempotency lookup shape.

`OperationsRepository.get_reconciliation_finding_summary(...)` builds the latest blocking finding
for a run by filtering `severity = 'ERROR'` and ordering by `created_at DESC, id DESC`. Existing
finding indexes supported run/type/severity counts, but not the run/severity/latest-blocker lookup
used by operator support summaries.

## Change

Added SQLAlchemy model indexes and Alembic migration
`c0d4e5f6a7b8_perf_add_control_query_lookup_indexes.py`:

1. `ix_analytics_export_jobs_dataset_fingerprint_id` on
   `analytics_export_jobs(dataset_type, request_fingerprint, id DESC)`,
2. `ix_financial_reconciliation_findings_run_severity_created_id` on
   `financial_reconciliation_findings(run_id, severity, created_at DESC, id DESC)`.

Added model index assertions and analytics export repository query-shape proof for the
dataset/fingerprint/latest-id lookup.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_analytics_export_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_analytics_export_repository.py alembic/versions/c0d4e5f6a7b8_perf_add_control_query_lookup_indexes.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_analytics_export_repository.py alembic/versions/c0d4e5f6a7b8_perf_add_control_query_lookup_indexes.py`

Results:

1. Focused model, analytics export, and operations repository proof: `75 passed`
2. Alembic head proof: `c0d4e5f6a7b8 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. Export idempotency and
reconciliation support-summary reads now have composite indexes aligned to their exact
filter-and-latest-row query shapes.
