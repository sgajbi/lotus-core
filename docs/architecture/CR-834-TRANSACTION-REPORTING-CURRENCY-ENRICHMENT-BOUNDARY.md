# CR-834: Transaction Reporting Currency Enrichment Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still owned field-level reporting-currency enrichment policy inline, including
the set of restatable transaction money fields and the rule for using trade currency versus book
currency.

Those rules are transaction ledger mapping policy. The service should coordinate repository reads
and supply the FX conversion boundary, not carry the field inventory itself.

## Change

Created `transaction_reporting_currency.py` and moved reporting-currency field enrichment into:

1. `apply_transaction_reporting_currency_fields(...)`,
2. `source_currency_for_transaction_field(...)`,
3. `TRANSACTION_REPORTING_CURRENCY_FIELDS`.

`TransactionService.get_transactions(...)` now delegates transaction record enrichment to the helper
and passes its existing `_convert_amount(...)` boundary. Direct field-mapping tests now live in
`test_transaction_reporting_currency.py`; service tests continue to prove orchestration and public
response behavior.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction filters or repository methods,
3. FX rate lookup and caching behavior,
4. reporting-currency calculation outputs,
5. realized tax summary aggregation,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service enrichment modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction service, metadata, realized-tax, and reporting-currency tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
