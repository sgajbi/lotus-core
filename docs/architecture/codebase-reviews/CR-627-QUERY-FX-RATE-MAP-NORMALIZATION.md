# CR-627: Query FX Rate Map Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Query-service FX-rate map builders in analytics-timeseries and reference-data repositories still
converted database row values with direct `Decimal(row.rate)` calls. These read paths already
bounded the query by normalized currency pair and date window, but sparse row evidence such as blank
or null rates could raise low-level decimal conversion errors before downstream callers could apply
their existing missing-FX handling.

## Change

Routed FX-rate row conversion through `decimal_or_none(...)` in both repository map builders.
Rows with blank or null rate evidence are omitted from the returned map, allowing downstream
analytics and source-data product services to surface the existing missing-FX behavior for that
date.

Added focused repository coverage for padded numeric text, blank rates, and null rates.

## Impact

This keeps FX-rate lookup evidence deterministic across analytics input generation, source-data
product extraction, gateway consumers, and performance/risk integrations while preserving SQL
predicates, ordering, returned map shape, and caller-level missing-rate behavior.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal repository normalization hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
