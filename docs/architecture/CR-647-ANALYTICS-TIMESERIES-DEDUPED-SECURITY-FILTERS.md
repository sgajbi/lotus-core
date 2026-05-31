# CR-647: Analytics Timeseries Deduped Security Filters

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Position analytics-timeseries repository helpers normalize security filters before building
position-timeseries, prior-position, snapshot-epoch, and position-cashflow queries. The request
contract accepts lists, so duplicate security IDs or duplicate position IDs could inflate the
generated `IN` predicates even though the returned analytics semantics are set-based for those
filters.

## Change

Deduplicated normalized security IDs in the shared repository helpers used by explicit
`security_ids` filters and portfolio-scoped `position_ids` filters. The service continues to
assemble one response row per returned timeseries row, so pagination, continuity repair, cashflow
attachment, and quality distribution behavior are unchanged.

## Impact

This reduces parameter volume and query planner work for duplicate-heavy position analytics reads
while preserving filter semantics, snapshot-epoch resolution, cursor behavior, cashflow enrichment,
response shape, and source-data product metadata.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal read-scope hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
