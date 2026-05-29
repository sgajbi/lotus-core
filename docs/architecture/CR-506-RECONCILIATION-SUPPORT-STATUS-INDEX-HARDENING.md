# CR-506: Reconciliation Support Status Index Hardening

Date: 2026-05-29

## Scope

Query-service operations support reads over financial reconciliation runs and findings.

## Finding

Reconciliation support APIs filtered run status and ranked finding severity by wrapping stored
values in `upper(trim(...))`. That matched defensive display semantics, but it prevented direct use
of the existing raw status and severity index columns. The persisted reconciliation service writes
governed uppercase status and severity values, so the read path can normalize caller input once and
compare directly against stored values.

The support run-list path also filters by `portfolio_id` and often by `status` before ordering by
latest `started_at`, but the existing composite index led with `reconciliation_type` instead of
portfolio.

## Change

1. Added `ix_financial_reconciliation_runs_port_status_started_id` on
   `(portfolio_id, status, started_at DESC, id ASC)`.
2. Added Alembic migration `c0e1f2a3b4c5_perf_add_reconciliation_run_support_index.py`.
3. Changed reconciliation run count/list status filters to normalize caller status once and compare
   directly against `financial_reconciliation_runs.status`.
4. Changed reconciliation finding ranking and summary logic to use governed stored severity values
   directly instead of wrapping severity in `upper(trim(...))`.
5. Added model and repository query-shape tests for the new index and index-friendly predicates.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e1f2a3b4c5_perf_add_reconciliation_run_support_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e1f2a3b4c5_perf_add_reconciliation_run_support_index.py`
6. `git diff --check`

Results:

1. Focused model and operations repository proof: `75 passed`
2. Alembic head proof: `c0e1f2a3b4c5 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This slice keeps
operations support reads aligned to governed stored status/severity vocabulary so reconciliation
control evidence remains index-friendly at banking scale.
