# CR-610: FX Rate Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The shared query-service FX converter still converted repository-returned rates inline with
`Decimal(str(...))`. That left a central read-path dependency on a separate numeric conversion
policy from adjacent reporting, cash, transaction, and core snapshot calculations.

## Change

Routed FX rate normalization through `decimal_or_none(...)` and treated blank rate evidence the
same as a missing rate, preserving the existing domain error path instead of leaking low-level
decimal conversion failures.

## Impact

This keeps FX rate handling consistent and conservative for sparse or malformed evidence while
preserving cache keys, identity conversion behavior, converted amount math, and error shape for
missing rates. API route shape, response fields, OpenAPI contracts, database schema, wiki source,
and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_fx_conversion.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
