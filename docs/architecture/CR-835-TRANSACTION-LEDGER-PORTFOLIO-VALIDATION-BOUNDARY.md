# CR-835: Transaction Ledger Portfolio Validation Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_transactions(...)` still duplicated the portfolio existence check and
`LookupError` message even though query-service now owns the shared
`portfolio_validation.ensure_portfolio_exists(...)` helper.

That kept transaction ledger reads carrying a local copy of the same validation contract already
used by position and booking-state services.

## Change

`TransactionService.get_transactions(...)` now routes portfolio existence validation through
`ensure_portfolio_exists(...)` before resolving the default ledger as-of date and repository filter
scope.

Focused service coverage proves the transaction ledger read path calls the shared helper. Existing
missing-portfolio coverage continues to prove the public exception contract.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction filters or repository methods,
3. default as-of date resolution,
4. projected transaction behavior,
5. reporting-currency enrichment,
6. realized-tax summary behavior,
7. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service validation modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction service, metadata, realized-tax, reporting-currency, and portfolio validation tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
