# CR-600: Core Snapshot Projection FX Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Core snapshot simulation projection already resolves portfolio-to-reporting FX before building
baseline and projected sections, but repricing new simulated positions fetched that same conversion
inside the projection loop. New positions in the same market currency also repeated identical
market-currency-to-portfolio FX lookups.

## Change

Passed the already resolved portfolio-to-reporting FX into projected-position resolution and added a
per-projection market-currency FX cache for priced new positions. The projection still resolves
market price per security and preserves the existing missing-price and missing-FX failure behavior.

## Impact

This reduces redundant FX repository calls in simulation snapshots that price multiple new
securities, especially model-portfolio or trade-list simulations with common market currencies. API
route shape, response fields, OpenAPI contracts, database schema, wiki source, and platform
contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
