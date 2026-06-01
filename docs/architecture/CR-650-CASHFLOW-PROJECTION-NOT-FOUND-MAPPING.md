# CR-650: Cashflow Projection Not Found Mapping

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The cashflow projection router correctly mapped portfolio-specific not-found messages to HTTP
`404`, but integration-lite also injects generic upstream `ValueError("not found")` failures to
prove router dependency behavior. That generic not-found shape was mapped to `400`, breaking the
route error contract.

## Change

Mapped any service `ValueError` whose message contains `not found` to HTTP `404` and kept all other
resolution errors, including horizon validation, mapped to HTTP `400`.

## Impact

This restores the route-level not-found contract for both concrete service messages and generic
dependency-injected not-found failures while preserving the cashflow projection horizon guard,
response shape, and OpenAPI examples.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/integration/services/query_service/test_cashflow_projection_router_dependency.py tests/unit/services/query_service/routers/test_cashflow_projection_router.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
