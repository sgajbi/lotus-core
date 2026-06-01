# CR-543: Operations Support Model Boundary

Date: 2026-05-31

## Scope

Query-service operations support repository and service-builder boundary.

## Finding

`operations_repository.py` mixed SQL repository behavior with immutable return-shape dataclasses
used by downstream service builders. That forced support overview, calculator SLO, portfolio
readiness, load-run progress, and operations service tests to import shared support models from the
SQL repository module even when they did not need repository behavior.

The coupling made the already-large operations repository harder to split safely and kept service
builders dependent on the persistence implementation module instead of a small model contract.

## Change

1. Added `operations_models.py` for immutable operations support summaries.
2. Moved job-health, reprocessing-health, reconciliation-finding, snapshot-coverage,
   missing-historical-FX, and load-run progress summary dataclasses into that module.
3. Updated service builders and their focused tests to import support models from the new model
   boundary.
4. Kept compatibility imports in `operations_repository.py` so existing repository consumers are
   not broken by the extraction.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_calculator_slo_builder.py tests/unit/services/query_service/services/test_support_overview_builder.py tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/repositories/operations_models.py src/services/query_service/app/services/operations_service.py src/services/query_service/app/services/support_overview_builder.py src/services/query_service/app/services/calculator_slo_builder.py src/services/query_service/app/services/load_run_progress_builder.py src/services/query_service/app/services/portfolio_readiness_builder.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_calculator_slo_builder.py tests/unit/services/query_service/services/test_support_overview_builder.py tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/repositories/operations_models.py src/services/query_service/app/services/operations_service.py src/services/query_service/app/services/support_overview_builder.py src/services/query_service/app/services/calculator_slo_builder.py src/services/query_service/app/services/load_run_progress_builder.py src/services/query_service/app/services/portfolio_readiness_builder.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_calculator_slo_builder.py tests/unit/services/query_service/services/test_support_overview_builder.py tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py`
6. `git diff --check`

Results:

1. Focused repository and service-builder proof passed.
2. Alembic reported a single current head.
3. Migration SQL contract smoke passed.
4. Touched-surface ruff passed.
5. Touched-surface format check passed.
6. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a modularity hardening slice that separates operations support model contracts from SQL
repository behavior while preserving compatibility for existing imports.
