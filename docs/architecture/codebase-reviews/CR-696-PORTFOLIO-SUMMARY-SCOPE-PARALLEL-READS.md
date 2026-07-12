# CR-696: Portfolio Summary Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`ReportingService.get_portfolio_summary(...)` resolved the portfolio before reading the latest
business date whenever callers omitted `as_of_date`. Those scope reads are independent for
default-date portfolio-summary requests, and the broader reporting service already uses parallel
scope resolution for AUM and allocation requests.

## Change

Default-date portfolio-summary requests now resolve portfolio metadata and the latest business date
with `asyncio.gather(...)`. Explicit `as_of_date` requests continue to skip the
latest-business-date lookup and use the caller-provided date.

Added focused coverage proving portfolio and default-date reads start concurrently, and that
explicit-date requests do not call the default-date lookup.

## Impact

This reduces `PortfolioSummary` latency for default-date reporting requests while preserving
portfolio validation, no-business-date failure behavior, snapshot aggregation, cash-account
breakdown reuse, FX conversion, response shape, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused reporting-service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
