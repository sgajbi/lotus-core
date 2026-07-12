# CR-663: Instrument Catalog Empty Window Read Skip

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`InstrumentService.get_instruments(...)` always issued the paged instrument query after the
filtered count query. When the count query returned zero, the service still executed the page read
even though the response was already known to contain no instruments.

This affected instrument/reference API reads where callers filter by a specific security ID or
product type and receive an empty catalog window.

## Change

Short-circuited empty instrument catalog windows after the count query:

1. keep the exact count query as the source of pagination truth,
2. skip `get_instruments(...)` when `total_count == 0`,
3. return the same paginated response shape with an empty `instruments` collection.

Added service coverage proving the zero-count path does not issue the page read.

## Impact

This removes an avoidable database read from empty instrument catalog requests while preserving
pagination metadata, identifier normalization, response shape, database schema, OpenAPI contracts,
and wiki source.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_instrument_service.py tests/unit/services/query_service/repositories/test_instrument_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
