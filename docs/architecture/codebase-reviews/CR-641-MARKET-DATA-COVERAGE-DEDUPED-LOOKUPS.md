# CR-641: Market Data Coverage Deduped Lookups

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`MarketDataCoverageWindow:v1` preserves one coverage record per requested instrument and currency
pair, but the latest-price and latest-FX repository lookups could receive duplicate normalized
instrument IDs or duplicate normalized currency pairs. Large DPM source-readiness requests with
overlapping held and target universes could therefore inflate SQL `IN` predicates without changing
the response.

## Change

Deduplicated normalized lookup scopes before calling the market-reference repository and added
repository-level deduplication as a defensive boundary for direct callers. Response assembly still
iterates over the original requested instruments and currency pairs.

## Impact

This reduces market/reference lookup parameter volume for duplicate-heavy DPM coverage requests
while preserving requested-count metadata, per-requested-item coverage rows, missing/stale
supportability semantics, latest evidence timestamp handling, lineage, and response shape.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal source-data product query-scope hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
