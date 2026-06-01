# CR-611: Integration Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Source-data product mapper normalization still converted required numeric values inline with
`Decimal(str(...))`. Because this helper is reused across reference-data and integration evidence
mappers, missing or blank required values could surface as low-level decimal conversion failures
instead of a deliberate mapper validation error.

## Change

Routed `as_decimal(...)` through `decimal_or_none(...)` and made missing or blank required numeric
values raise a clear `ValueError`. Existing `Decimal` preservation and stringable numeric
conversion behavior remain unchanged.

## Impact

This keeps source-data product evidence normalization aligned with the query-service decimal helper
while preserving strict required-field behavior. API route shape, response fields, OpenAPI
contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal mapper normalization with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_integration_value_normalization.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
