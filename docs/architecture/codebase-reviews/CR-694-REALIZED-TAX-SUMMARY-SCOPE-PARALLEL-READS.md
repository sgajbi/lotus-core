# CR-694: Realized Tax Summary Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService.get_realized_tax_summary(...)` resolved the portfolio base currency before
reading the latest business date whenever callers omitted `as_of_date`. Those scope reads are
independent for default-date realized-tax summary requests, so source-data tax evidence assembly
serialized setup before reading transaction counts and realized-tax rows.

## Change

Default-date realized-tax summary requests now resolve portfolio base currency and latest business
date with `asyncio.gather(...)`. Explicit `as_of_date` requests continue to skip the
latest-business-date lookup and use the caller-provided date.

Added focused coverage proving base-currency and default-date reads start concurrently, and that
explicit-date requests do not call the default-date lookup.

## Impact

This reduces `PortfolioRealizedTaxSummary` latency for default-date source-data requests while
preserving portfolio validation, explicit-date behavior, transaction count/evidence concurrency,
currency normalization, reporting-currency conversion behavior, response shape, database schema,
wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused realized-tax summary proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
