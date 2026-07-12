# CR-838: Transaction Ledger Filter Shape Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still constructed transaction repository filter dictionaries inline for both
the full transaction ledger window and realized-tax summary reads.

Those dictionaries define repository request shape for transaction-derived source-data products and
should be explicit, reusable, and directly tested outside service orchestration.

## Change

Added transaction filter helpers to `transaction_metadata.py`:

1. `transaction_ledger_filters(...)`,
2. `realized_tax_summary_filters(...)`.

`TransactionService` now delegates repository filter construction to those helpers. Direct metadata
tests prove exact key shape and value preservation while existing service tests continue to prove
repository calls receive the same filters.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. repository method names,
3. transaction ledger filter values,
4. realized-tax summary filter values,
5. as-of date resolution,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service repository-request
modularity hardening and does not change operator workflow, supported feature behavior, API usage,
or runtime commands.

## Validation

Local validation passed for the slice:

1. focused transaction service, metadata, realized-tax, reporting-currency, and portfolio validation tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
