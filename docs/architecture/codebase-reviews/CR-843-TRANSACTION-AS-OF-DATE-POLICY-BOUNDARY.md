# CR-843: Transaction As-Of Date Policy Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still owned transaction-ledger and realized-tax effective as-of date policy
inline. That included:

1. explicit as-of date precedence,
2. projected ledger reads preserving `None`,
3. latest business date defaults,
4. current-date fallback when the repository has no latest business date.

Those policies are reusable transaction source-data read policies and should be directly tested
outside service orchestration.

## Change

Created `transaction_dates.py` with:

1. `transaction_ledger_effective_as_of_date(...)`,
2. `realized_tax_effective_as_of_date(...)`.

`TransactionService` now delegates transaction ledger and realized-tax effective as-of date
resolution to those helpers. Direct date-policy tests prove explicit date precedence, projected
ledger behavior, latest business date lookup, and deterministic today fallback for both relevant
transaction source-data products.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. repository predicates,
3. projected transaction ledger behavior,
4. realized-tax summary as-of date behavior,
5. reporting-currency conversion semantics,
6. source-data-product runtime metadata semantics,
7. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service date-policy modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction date-policy and service tests,
2. focused transaction service, date, metadata, realized-tax, reporting-currency, read, record, and
   portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
