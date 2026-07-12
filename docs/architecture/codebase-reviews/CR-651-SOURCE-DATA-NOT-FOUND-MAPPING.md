# CR-651: Source Data Not Found Mapping

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cash-balance and liquidity-ladder source-data routes still mapped only portfolio-shaped
`ValueError` messages to HTTP `404`. Generic dependency-injected not-found failures could therefore
surface as `400` even though the route contract documents missing source scope as not found.

## Change

Added a shared query-service router helper that maps service `ValueError` messages containing
`not found` to HTTP `404` and all other resolution errors to HTTP `400`. Routed cash balances,
cashflow projection, and liquidity ladder through the helper, preserving existing OpenAPI examples
and service behavior.

## Impact

This keeps not-found behavior consistent across high-use source-data read products while preserving
business-date, horizon, FX, and other validation failures as client-correctable `400` responses.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/routers/test_http_errors.py tests/integration/services/query_service/test_cash_balances_router.py tests/integration/services/query_service/test_liquidity_ladder_router.py tests/integration/services/query_service/test_cashflow_projection_router_dependency.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
