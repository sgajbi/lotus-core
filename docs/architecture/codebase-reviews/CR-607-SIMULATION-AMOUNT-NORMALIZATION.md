# CR-607: Simulation Amount Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Simulation projected-position reads still converted baseline quantities, optional cost values, and
simulation change amount fields inline with `Decimal(str(...))`. That kept an important what-if
calculation path on a separate numeric normalization policy after query-service amount conversion
was centralized.

## Change

Added `decimal_or_none(...)` next to `decimal_or_zero(...)` for optional numeric fields that must
preserve null semantics. Routed simulation baseline quantity/cost normalization and change-record
quantity, price, and amount normalization through the shared helpers.

## Impact

This keeps simulation quantity and optional amount handling consistent with the rest of the
query-service calculation layer while preserving response shape and `None` semantics for absent
optional values. API route shape, response fields, OpenAPI contracts, database schema, wiki source,
and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_simulation_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
