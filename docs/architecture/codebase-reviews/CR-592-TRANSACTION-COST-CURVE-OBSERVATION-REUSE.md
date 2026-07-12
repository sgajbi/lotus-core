# CR-592: Transaction Cost Curve Observation Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The transaction cost curve bulk builder still computed usable cost observations while grouping
transactions and then recomputed the same fee amount, notional, and evidence eligibility checks
again when building each curve point. This affects transaction-cost evidence support paths where
large portfolio transaction histories can be scanned to produce source-data evidence for execution
cost curves.

## Change

Kept `build_transaction_cost_curve_point(...)` behavior unchanged for direct callers, but routed
the bulk `build_transaction_cost_curve_points(...)` path through precomputed `_CostObservation`
instances. Added focused coverage proving the bulk path stringifies the notional source value once,
which guards against reintroducing duplicate Decimal conversion work.

## Impact

This reduces repeated calculation work on transaction-cost evidence aggregation without changing
API route shape, response fields, OpenAPI contracts, database schema, wiki source, or platform
contracts.

No wiki update was needed because this is internal calculation-path optimization with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
