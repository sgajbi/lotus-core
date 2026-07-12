# CR-836: Transaction Service Session State Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still retained the raw `AsyncSession` on `self.db` even though all runtime reads
go through `TransactionRepository` and `CachedFxRateConverter`.

Keeping unused session state widens the service object surface and makes dependency flow less
explicit.

## Change

Removed the unused `self.db` assignment from `TransactionService.__init__(...)`.

Focused coverage now proves the service constructs `TransactionRepository` from the supplied
session, wires `CachedFxRateConverter`, and does not retain the raw session.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction filters or repository methods,
3. FX conversion behavior,
4. transaction ledger validation,
5. realized-tax summary behavior,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal service dependency-flow hardening and does
not change operator workflow, supported feature behavior, API usage, or runtime commands.

## Validation

Local validation passed for the slice:

1. focused transaction service, metadata, realized-tax, reporting-currency, and portfolio validation tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
