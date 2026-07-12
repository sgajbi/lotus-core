# CR-598: Shared FX Conversion Cache

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cash balance and reporting services each carried their own FX conversion cache, normalization, and
missing-rate error handling. These services support high-use portfolio reporting paths, and
duplicated cache logic increases drift risk across AUM, allocation, portfolio summary, and cash
balance responses.

## Change

Added `fx_conversion.py` with a tested `CachedFxRateConverter` and routed cash balance and
reporting service conversion wrappers through it. Existing service wrapper methods remain in place
so internal call sites and tests keep their current shape while the conversion logic is centralized.

## Impact

This reduces duplicated FX conversion infrastructure across query-service reporting paths and keeps
normalization, cache lookup, identity conversion, and missing-rate failure behavior directly tested.
API route shape, response fields, OpenAPI contracts, database schema, wiki source, and platform
contracts are unchanged.

No wiki update was needed because this is internal service-boundary reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_fx_conversion.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
