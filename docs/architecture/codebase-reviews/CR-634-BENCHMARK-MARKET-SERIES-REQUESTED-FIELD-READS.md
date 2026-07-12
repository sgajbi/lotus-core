# CR-634: Benchmark Market Series Requested-Field Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Benchmark market-series source-data product assembly accepted explicit `series_fields`, but still
read index price, index return, and benchmark return evidence for the page even when the caller did
not request those fields. Broad benchmark requests that only needed benchmark return, component
weight, or FX context therefore paid unnecessary repository and database read cost.

## Change

Routed index price, index return, and benchmark return repository calls through the requested field
set. FX-only requests can now use FX-rate dates as the point date source instead of depending on
unrequested market evidence reads to create points.

## Impact

This reduces source-data product read amplification for benchmark market-series requests while
preserving page-scoped component reads, page-token semantics, response field gating, FX context,
quality diagnostics, and response shape for requested fields.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal read-path performance hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
