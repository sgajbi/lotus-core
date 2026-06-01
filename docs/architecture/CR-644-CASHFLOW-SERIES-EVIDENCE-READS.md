# CR-644: Cashflow Series Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cashflow projection and liquidity ladder reads fetched booked cashflow series, projected settlement
series, and then ran separate latest-evidence timestamp queries over the same booked/projected
scopes. Include-projected requests therefore repeated the cashflow and transaction evidence scans
only to recover source timestamps.

## Change

Added repository helpers that return daily cashflow series and latest evidence timestamp together:

1. `get_portfolio_cashflow_series_with_evidence(...)`
2. `get_projected_settlement_cashflow_series_with_evidence(...)`

The existing two-column series methods remain as compatibility wrappers. Cashflow projection and
liquidity ladder now derive `latest_evidence_timestamp` from the series reads and no longer call the
standalone timestamp query on their hot paths.

## Impact

This removes redundant booked/projected evidence scans for cashflow projection and liquidity ladder
requests while preserving latest-restatement semantics, projected external settlement predicates,
daily aggregation, source metadata, response shape, and compatibility for existing repository
callers.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal repository/service read-shape hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py tests/unit/services/query_service/services/test_cashflow_projection_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
