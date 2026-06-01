# CR-680: Transaction Reporting Currency Parallel Conversions

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService._apply_reporting_currency_fields(...)` converted each populated transaction
money field sequentially when a `TransactionLedgerWindow` request supplied `reporting_currency`.
Those conversions are independent once the source currency basis for each field is known. On
ledger pages with trade, cost, realized PnL, and interest-tax fields, the sequential loop added
avoidable latency while relying on repeated calls into the FX converter.

## Change

The service now builds the populated money-field conversion requests first, resolves them with
`asyncio.gather(...)`, and then assigns converted values back to the response DTO in deterministic
field order. This composes with the branch's in-flight FX de-duplication so same-key concurrent
conversions still share one repository FX lookup.

Added service coverage that would deadlock under sequential execution, proving populated
transaction money-field conversions are started concurrently.
While touching this service, local return typing for ledger quality, source-currency, and FX
conversion helpers was made explicit for the repo typechecker.

## Impact

This reduces reporting-currency enrichment latency for populated transaction ledger pages while
preserving source-currency selection, same-currency conversion, missing-rate failure behavior,
response shape, pagination, evidence metadata, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused transaction-service reporting-currency proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m mypy --config-file mypy.ini`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
