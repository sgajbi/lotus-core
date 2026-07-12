# CR-612: Core Snapshot Price FX Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Core snapshot projected-position repricing still converted market prices and FX rates inline with
`Decimal(str(...))`. Blank price or rate evidence could therefore leak low-level decimal conversion
failures from a high-use source-data product path.

## Change

Added a core snapshot `_required_decimal(...)` guard backed by `decimal_or_none(...)`, routed
projected-position price normalization and core snapshot FX-rate normalization through it, and
preserved the existing domain-specific unavailable-section error messages for missing evidence.

## Impact

This removes the remaining inline Decimal conversions from query-service core snapshot code while
keeping missing price and FX-rate behavior explicit and user-facing. API route shape, response
fields, OpenAPI contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
