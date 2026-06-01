# CR-660: Benchmark Market Series Paging Contract Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_benchmark_market_series(...)` still treated
`list_benchmark_component_index_ids_overlapping_window(...)` as an optional repository capability.
When absent, the service fell back to loading every benchmark component overlapping the requested
window and only then applied page-token filtering in memory.

For large composite benchmarks, that fallback could turn a page-scoped market-data request into a
full-window component read before downstream price/return evidence collection. The production
reference repository already exposes the page-scoped component index-id query.

## Change

Removed the optional capability branch and made benchmark market-series assembly use the active
repository contract directly:

1. page component `index_id` values through
   `list_benchmark_component_index_ids_overlapping_window(...)`,
2. fetch benchmark composition rows only for the page-scoped `index_ids`,
3. derive downstream index price/return evidence from that page-scoped component set.

Updated integration-service tests so repository doubles provide the same benchmark component
paging method used in production.

## Impact

This keeps `MarketDataWindow` reads bounded by the requested page and prevents a stale fallback from
reintroducing full-window component fan-out. API response shape, page-token semantics, source-data
runtime metadata, database schema, OpenAPI contracts, and wiki source are unchanged.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
