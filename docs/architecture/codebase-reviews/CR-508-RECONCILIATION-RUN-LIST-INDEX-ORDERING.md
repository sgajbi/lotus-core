# CR-508: Reconciliation Run List Index Ordering

Date: 2026-05-29

## Scope

Financial reconciliation run-list queries used by the reconciliation service API.

## Finding

`ReconciliationRepository.list_runs(...)` filters by `portfolio_id` and optionally
`reconciliation_type`, then returns the latest runs by `started_at DESC`. The table had single
column indexes plus adjacent support indexes, but no composite index matching the common
portfolio/type/latest-run list shape.

The query also lacked a deterministic id tie-breaker, so runs with identical `started_at` values
could page or display in unstable order.

## Change

1. Added `ix_financial_reconciliation_runs_port_type_started_id` on
   `(portfolio_id, reconciliation_type, started_at DESC, id DESC)`.
2. Added Alembic migration `c0e3f4a5b6c7_perf_add_reconciliation_run_list_index.py`.
3. Updated `list_runs(...)` to order by `started_at DESC, id DESC`.
4. Added model metadata and repository query-shape tests for the new index-aligned order.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py alembic/versions/c0e3f4a5b6c7_perf_add_reconciliation_run_list_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py alembic/versions/c0e3f4a5b6c7_perf_add_reconciliation_run_list_index.py`
6. `git diff --check`

Results:

1. Focused model and reconciliation repository proof: `16 passed`
2. Alembic head proof: `c0e3f4a5b6c7 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is a storage/index
and deterministic-order hardening change for an existing reconciliation control endpoint.
