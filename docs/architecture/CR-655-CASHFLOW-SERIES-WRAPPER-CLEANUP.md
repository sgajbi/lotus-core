# CR-655: Cashflow Series Wrapper Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashflowRepository` still exposed row-only cashflow series wrapper methods after cashflow
projection and liquidity ladder moved to `*_with_evidence` reads. Those wrappers had no production
callers and could encourage future code to lose source-evidence metadata.

## Change

Removed the unused row-only booked and projected cashflow series wrappers and updated the
repository integration proof to call the active evidence-returning booked series method directly.

## Impact

This keeps cashflow read paths aligned to source-data product metadata requirements and reduces
stale repository surface area without changing API response shape or database schema.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py tests/unit/services/query_service/services/test_cashflow_projection_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py tests/integration/services/query_service/test_integration_cashflow_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
