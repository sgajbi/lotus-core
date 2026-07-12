# CR-415: Portfolio Manager Book Status Normalization

Date: 2026-05-28

## Scope

Query-service portfolio repository portfolio-manager book membership filtering.

## Finding

`list_portfolio_manager_book_members(...)` used open/close dates plus a raw
`Portfolio.status == "ACTIVE"` predicate when `include_inactive` was false. Casing or whitespace
drift in portfolio master status could exclude a valid active discretionary mandate from the
portfolio manager book, which would weaken downstream DPM source-data products and private-banking
operator views that depend on Core as the authoritative portfolio membership source.

## Change

Added a repository-level portfolio status expression using `upper(trim(status))` and reused it for
active portfolio-manager book membership filtering. Updated the query-shape test to lock the
normalized active-status predicate and preserve the `include_inactive` bypass behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_portfolio_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/portfolio_repository.py tests/unit/services/query_service/repositories/test_query_portfolio_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
query repository reliability slice that keeps private-banking portfolio-manager book membership
stable when persisted portfolio status control codes drift.
