# CR-527: Portfolio Status Identity Helper Cleanup

Date: 2026-05-31

## Scope

Query-service portfolio master repository status handling for portfolio-manager book membership
source-data reads.

## Finding

`PortfolioRepository.list_portfolio_manager_book_members(...)` is a source-data product hot path for
portfolio-manager book membership evidence. After portfolio status predicates moved to governed
stored values, the repository still retained a private `_portfolio_status_expr(...)` helper that
returned the input column unchanged.

The helper no longer encoded normalization or query behavior, but it preserved stale guidance that
portfolio master status reads might still require a repository-local expression layer.

## Change

1. Removed the identity-only portfolio status expression helper.
2. Compared `Portfolio.status` directly against the governed stored `ACTIVE` lifecycle value.
3. Preserved the existing active-membership temporal predicates and deterministic portfolio-id
   ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_portfolio_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/portfolio_repository.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/portfolio_repository.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py`
4. `rg "_portfolio_status_expr" src/services/query_service/app/repositories/portfolio_repository.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py -n`
5. `git diff --check`

Results:

1. Focused portfolio repository proof passed.
2. Touched-surface ruff passed.
3. Touched-surface format check passed.
4. Dead-helper search returned no matches.
5. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability cleanup that keeps portfolio source-data evidence reads aligned with the
governed stored-value contract.
