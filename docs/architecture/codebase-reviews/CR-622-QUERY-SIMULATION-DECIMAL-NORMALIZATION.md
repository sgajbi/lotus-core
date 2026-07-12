# CR-622: Query Simulation Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After the shared decimal-normalization pass, the remaining production `Decimal(str(...))` calls were
concentrated in query-service precision, advisory simulation FX valuation, and simulation-change
repository persistence. These paths sit on read/calculation workflows used by advisory simulations
and snapshot projections.

## Change

Routed the remaining production query-service conversions through shared decimal helpers:

1. query-service and advisory precision policies now use shared optional decimal parsing while
   preserving `None` as zero and blank/invalid input rejection,
2. advisory simulation FX conversion now reuses the advisory precision decimal guard for direct and
   inverse rates,
3. simulation-change repository persistence now uses optional decimal normalization for quantity,
   price, and amount fields.

Focused tests cover blank-input rejection in both precision policies, numeric text FX rates in
advisory valuation, and blank optional simulation-change amount fields.

## Impact

This removes the last production `Decimal(str(...))` conversions from `src/services` and `src/libs`
while preserving rounding policy, advisory valuation behavior, and simulation-change response shape.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal numeric normalization and repository persistence
hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/test_precision_policy.py tests/unit/services/query_service/test_rounding_golden_vectors.py tests/unit/services/query_service/advisory_simulation/test_advisory_precision_policy.py tests/unit/services/query_service/advisory_simulation/test_valuation.py tests/unit/services/query_service/repositories/test_simulation_repository.py tests/unit/services/query_service/services/test_simulation_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `rg "Decimal\(str\(" src/services src/libs -n`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
