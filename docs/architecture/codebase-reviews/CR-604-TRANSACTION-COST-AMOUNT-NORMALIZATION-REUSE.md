# CR-604: Transaction Cost Amount Normalization Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Transaction-cost curve calculation still carried a private `_as_decimal(...)` helper after
query-service amount normalization was centralized. That kept transaction-cost fee and notional
observation logic on a separate numeric normalization path from cash, liquidity, reporting, and
simulation calculation helpers.

## Change

Routed transaction-cost fee and notional normalization through `decimal_or_zero(...)` and removed
the private converter. Added coverage for blank explicit cost values so sparse transaction-cost
evidence remains fail-soft instead of raising during curve construction.

## Impact

This keeps amount normalization consistent across source-data product calculation paths while
preserving observed-cost precedence, usable-observation filtering, cost-bps math, and deterministic
curve-point construction. API route shape, response fields, OpenAPI contracts, database schema,
wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
