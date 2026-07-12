# CR-632: Benchmark Market Series Page-Scoped Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Benchmark market-series source-data product assembly discovered every component index in the
requested window, fetched index price and return evidence for all of them, and only then applied
component pagination. Broad composite benchmarks could therefore read and rank evidence rows for
components outside the returned page.

## Change

Added a bounded repository helper that lists distinct benchmark component index IDs for an
overlapping composition window using the existing benchmark/effective-window predicates,
cursor-after `index_id` pagination, and `page_size + 1` lookahead. The market-series service now
uses that helper when available, fetches composition rows only for the returned page's component
IDs, and sends those same IDs to the index price and return evidence queries.

Fallback behavior remains for test doubles or alternate repositories without the new helper.

## Impact

This reduces source-data product read amplification for benchmark market-series evidence while
preserving page-token semantics, component ordering, benchmark return context, FX context,
quality-summary scoping, response shape, and diagnostics.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal read-path performance hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
