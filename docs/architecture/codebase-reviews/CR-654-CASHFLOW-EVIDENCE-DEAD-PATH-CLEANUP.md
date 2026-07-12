# CR-654: Cashflow Evidence Dead Path Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After cashflow projection and liquidity ladder reads moved to series-with-evidence repository
methods, `CashflowRepository.get_latest_cashflow_evidence_timestamp(...)` no longer had production
callers. The only remaining references were repository tests for the stale method and service tests
asserting that mocks did not await it.

## Change

Removed the unused repository method, deleted its dedicated tests, and removed residual service mock
assertions that only referenced the dead API.

## Impact

This keeps cashflow evidence metadata ownership on the active series-with-evidence reads and removes
a misleading duplicate timestamp query path from the query-service repository surface.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py tests/unit/services/query_service/services/test_cashflow_projection_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
