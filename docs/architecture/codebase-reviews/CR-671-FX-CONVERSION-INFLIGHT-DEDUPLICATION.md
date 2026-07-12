# CR-671: FX Conversion In-Flight Deduplication

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CachedFxRateConverter` cached resolved FX rates after a repository lookup completed, but concurrent
requests for the same normalized currency pair and as-of date could all miss the cache before the
first lookup returned. That created avoidable duplicate FX reads on shared reporting, cash, and
transaction read paths.

## Change

The converter now tracks one in-flight lookup per normalized `(from_currency, to_currency,
as_of_date)` key. Concurrent callers await the same protected task, successful lookups populate the
resolved-rate cache once, and missing or blank FX evidence still raises without being cached.

The slice intentionally does not parallelize row-level reporting conversions yet. Distinct FX pairs
can still require distinct repository reads, and unrestricted fan-out through a shared async session
needs either bulk FX prefetching or a session-safe repository contract before it is bank-grade.

## Impact

This removes duplicate same-key FX repository reads during concurrent query-service response
assembly while preserving identity conversion, normalization, missing-rate behavior, response
contracts, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused FX conversion concurrency proof
2. focused reporting service proof
3. focused cash balance service proof
4. focused transaction service proof
5. `python -m alembic heads`
6. `python scripts/migration_contract_check.py --mode alembic-sql`
7. touched-surface `python -m ruff check`
8. touched-surface `python -m ruff format --check`
9. `git diff --check`
