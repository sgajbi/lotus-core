# CR-844: Transaction FX Rate Accessor Dead Code

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still exposed a private `_get_fx_rate(...)` method after transaction
reporting-currency behavior had been routed through `_convert_amount(...)` and the shared
`CachedFxRateConverter`.

Search evidence showed the method was only used by a transaction-service unit test. Keeping a
test-only service method widened the service surface without supporting runtime transaction
behavior.

## Change

Removed `TransactionService._get_fx_rate(...)`.

Updated the focused transaction-service FX test to verify the behavior the service actually owns:
same-currency `_convert_amount(...)` delegation through `CachedFxRateConverter` without repository
FX lookup. Shared FX rate normalization, missing-rate behavior, and cache behavior remain covered by
`test_fx_conversion.py`.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction ledger reporting-currency conversion behavior,
3. realized-tax reporting-currency conversion behavior,
4. shared `CachedFxRateConverter` behavior,
5. repository method names,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change removes internal transaction-service dead code and
does not change operator workflow, supported feature behavior, API usage, or runtime commands.

## Validation

Local validation passed for the slice:

1. focused transaction service and shared FX converter tests,
2. focused transaction service, date, metadata, realized-tax, reporting-currency, read, record, FX,
   and portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
