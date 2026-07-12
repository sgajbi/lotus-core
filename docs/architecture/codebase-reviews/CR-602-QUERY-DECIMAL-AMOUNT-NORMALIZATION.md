# CR-602: Query Decimal Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Liquidity ladder and position-flow calculation paths each carried local amount-to-`Decimal`
normalization helpers. That duplicated null/blank handling and conversion behavior across
calculation paths that process snapshot market values, cashflow series amounts, and simulation
transaction effects.

## Change

Added a shared `decimal_amounts.py` helper for query-service calculation paths and routed liquidity
ladder and position-flow effect code through it. The helper preserves existing `Decimal` instances,
normalizes null and blank inputs to zero, and stringifies non-Decimal values once.

## Impact

This reduces duplicated numeric normalization code across high-use read/calculation paths and keeps
blank/null behavior directly tested. API route shape, response fields, OpenAPI contracts, database
schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_position_flow_effects.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
