# CR-626: Analytics Timeseries Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Query-service analytics timeseries response assembly still converted portfolio and position
timeseries row values with direct `Decimal(row.value)` calls. That left product-facing source-data
payload generation inconsistent with the query-service decimal normalization policy already used by
cash, reporting, simulation, snapshot, and FX calculation paths.

Sparse or driver-normalized database row evidence such as `None`, blank text, or padded numeric text
could therefore fail differently from adjacent query-service paths even though these fields are
zero-default amount evidence in the response assembly path.

## Change

Routed portfolio cashflow amounts, position cashflow amounts, beginning and ending market values,
prior EOD cache values, position BOD flow values, and position quantities through the existing
`decimal_or_zero(...)` helper before arithmetic or DTO construction.

Added focused analytics-timeseries service coverage for sparse portfolio and position numeric rows.

## Impact

This keeps analytics input payload generation deterministic for API consumers, gateway integrations,
performance/risk consumers, and source-data product evidence exports while preserving response shape,
FX conversion behavior, pagination, snapshot epoch semantics, and quality diagnostics.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal response-assembly hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
