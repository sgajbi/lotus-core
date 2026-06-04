# CR-831: BUY/SELL State Portfolio Validation Boundary

Status: Hardened on 2026-06-02.

## Finding

`BuyStateService` and `SellStateService` each carried local copies of the same portfolio existence
guard already centralized by `portfolio_validation.ensure_portfolio_exists(...)`.

The duplicated guard preserved behavior, but it made booking-state service methods responsible for a
cross-cutting validation contract that should remain reusable across query-service read modules.

## Change

The BUY and SELL state services now route portfolio existence checks through
`ensure_portfolio_exists(...)` before executing state-specific repository reads.

Focused tests prove the services call the shared validation helper, while existing missing-portfolio
tests continue to prove the public `LookupError` contract.

## Boundary Preserved

This change does not alter:

1. API routes or response DTOs,
2. repository methods or query predicates,
3. security identifiers or normalization behavior,
4. database schema or migrations,
5. BUY/SELL cash-linkage or disposal arithmetic.

## No Wiki Change

No wiki source update is required. The change is internal query-service modularity hardening and does
not change operator workflow, supported feature behavior, API usage, or runtime commands.

## Validation

Local validation passed for the slice:

1. focused BUY/SELL state service tests,
2. shared portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
