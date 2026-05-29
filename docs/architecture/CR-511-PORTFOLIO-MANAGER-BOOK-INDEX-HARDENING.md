# CR-511: Portfolio Manager Book Index Hardening

Date: 2026-05-29

## Scope

Query-service portfolio manager book membership reads.

## Finding

`PortfolioRepository.list_portfolio_manager_book_members(...)` is a front-office/private-banking
hot path: it resolves the portfolios owned by an advisor or portfolio manager for an as-of date.
The query always filters by `advisor_id`, commonly filters active book membership by status and
open/close date, and returns deterministic `portfolio_id` ordering.

The `portfolios` table had indexes for portfolio identity and booking center, but no composite index
matching the advisor book membership shape. The active-status predicate also wrapped stored status
values in `upper(trim(...))`, making the persisted status contract less explicit.

## Change

1. Added `ix_portfolios_advisor_status_open_close_portfolio` on
   `(advisor_id, status, open_date, close_date, portfolio_id)`.
2. Added Alembic migration `c0e6f7a8b9c0_perf_add_pm_book_portfolio_index.py` to normalize existing
   portfolio statuses and create the composite index.
3. Changed the PM book active-status predicate to compare directly against governed stored status
   values.
4. Added model metadata and repository query-shape proof for the new index-aligned predicate.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/portfolio_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py alembic/versions/c0e6f7a8b9c0_perf_add_pm_book_portfolio_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/portfolio_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py alembic/versions/c0e6f7a8b9c0_perf_add_pm_book_portfolio_index.py`
7. `git diff --check`

Results:

1. Focused model and portfolio repository proof: `17 passed`
2. Broader model and query-service repository proof: `218 passed`
3. Alembic head proof: `c0e6f7a8b9c0 (head)`
4. Migration contract smoke: passed
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is an index and
storage-contract hardening change for an existing advisor book membership query.
