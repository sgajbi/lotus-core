# CR-833: Realized Tax Aggregation Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still owned pure realized-tax aggregation policy inline through a private
accumulator and helper method.

That policy belongs to the `PortfolioRealizedTaxSummary` source-data product boundary, not to the
service orchestration layer that coordinates repository reads, runtime metadata, and reporting
currency conversion.

## Change

Created `transaction_realized_tax.py` and moved realized-tax currency aggregation into
`realized_tax_currency_totals(...)`.

`TransactionService.get_realized_tax_summary(...)` now delegates currency bucket construction to
that helper. Direct aggregation tests now live in `test_transaction_realized_tax.py`; service tests
continue to prove the public realized-tax summary response behavior.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. portfolio, date, or as-of transaction filters,
3. realized-tax inclusion rules,
4. reporting-currency conversion behavior,
5. data-quality or evidence timestamp metadata,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service aggregation modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction service, metadata, and realized-tax tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
