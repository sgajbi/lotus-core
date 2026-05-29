# CR-507: Reconciliation Finding List Index Ordering

Date: 2026-05-29

## Scope

Financial reconciliation finding-list queries used by the reconciliation service API.

## Finding

`ReconciliationRepository.list_findings(...)` filters by `run_id` and orders findings by
`severity ASC`, `finding_type ASC`, and `id ASC`. The existing composite index was ordered as
`run_id, finding_type, severity`, which did not match the actual list order and left the API less
prepared for high-volume reconciliation runs with many findings.

CR-506 added index-friendly support reads in the query-service operations plane. This slice closes
the matching issue on the reconciliation service's own finding-list endpoint.

## Change

1. Replaced `ix_financial_reconciliation_findings_run_type_severity` with
   `ix_financial_reconciliation_findings_run_severity_type_id`.
2. Added Alembic migration `c0e2f3a4b5c6_perf_reorder_reconciliation_finding_index.py`.
3. Added model metadata proof for the new ordered index.
4. Added repository query-shape proof that `list_findings(...)` preserves the index-aligned order.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py alembic/versions/c0e2f3a4b5c6_perf_reorder_reconciliation_finding_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py alembic/versions/c0e2f3a4b5c6_perf_reorder_reconciliation_finding_index.py`
6. `git diff --check`

Results:

1. Focused model and reconciliation repository proof: `15 passed`
2. Alembic head proof: `c0e2f3a4b5c6 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is a storage/index
alignment change for an existing governed reconciliation endpoint.
