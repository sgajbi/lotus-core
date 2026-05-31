# CR-685: Reporting Scope Date Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`ReportingService._resolve_scope_portfolios_and_date(...)` resolved the latest business date before
reading the portfolio scope whenever callers omitted `as_of_date`. The date lookup and portfolio
scope lookup are independent inputs for AUM, allocation, and reporting-oriented query paths.

## Change

When `as_of_date` is omitted, the helper now reads the latest business date and matching
portfolios with `asyncio.gather(...)`. Explicit `as_of_date` requests still skip the latest-date
lookup and only read matching portfolios.

Added service coverage that would deadlock under sequential execution, proving default-date and
portfolio-scope reads are started concurrently.

## Impact

This reduces shared reporting read-path latency for default-date AUM and allocation requests while
preserving explicit-date behavior, missing-date validation priority, empty-scope validation,
response shape, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service scope/date proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
