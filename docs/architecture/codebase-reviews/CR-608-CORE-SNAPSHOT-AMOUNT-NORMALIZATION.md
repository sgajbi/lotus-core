# CR-608: Core Snapshot Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Core snapshot baseline and projected position calculations still carried inline
`Decimal(str(...))` conversions for position quantities, optional market values, optional fallback
cost values, transaction effects, and total-market-value helpers. That kept a high-use source-data
product path on a separate conversion policy from the shared query-service amount helpers.

## Change

Routed baseline position quantities and optional value fields through `decimal_or_zero(...)` and
`decimal_or_none(...)`, reused the decimal transaction-effect result directly, and aligned
baseline/projected total helpers with the shared conversion helpers.

## Impact

This keeps core snapshot numeric normalization consistent across baseline and simulation sections
while preserving response shape, optional-value `None` semantics, and existing fallback behavior.
API route shape, response fields, OpenAPI contracts, database schema, wiki source, and platform
contracts are unchanged.

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
