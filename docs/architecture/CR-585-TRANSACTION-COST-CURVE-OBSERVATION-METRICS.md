# CR-585: Transaction Cost Curve Observation Metrics

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After CR-583 extracted transaction-cost curve construction into a helper, point assembly still
recomputed the same fee and notional values several times per transaction row. It also relied on
the group builder to have prefiltered every row before direct point construction. That was safe for
the service path but left the helper easier to misuse and more expensive than necessary on large
observed cost groups.

## Change

Added a private `_CostObservation` metrics record and a single `_cost_observation(...)` resolver
for each row. The helper now:

1. resolves explicit-cost-row versus `trade_fee` precedence once,
2. resolves absolute gross notional once,
3. filters unusable zero-fee or zero-notional rows before aggregate math,
4. calculates total cost, total notional, average/min/max bps, dates, and sample ids from the same
   observed-row metrics list.

## Impact

This reduces repeated decimal/fee calculations and hardens direct point construction against
unusable rows without changing the query, API route shape, response fields, OpenAPI contracts,
database schema, wiki source, or platform contracts.

No wiki update was needed because this is internal source-data product calculation hardening with
no operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
