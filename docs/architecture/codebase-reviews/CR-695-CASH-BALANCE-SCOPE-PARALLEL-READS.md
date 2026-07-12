# CR-695: Cash Balance Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashBalanceService.get_cash_balances(...)` resolved the portfolio before reading the latest
business date whenever callers omitted `as_of_date`. Those scope reads are independent for
default-date cash-balance source-data requests, so the service serialized setup before reading the
latest cash snapshot rows and cash-account master evidence.

## Change

Default-date cash-balance requests now resolve portfolio metadata and the latest business date with
`asyncio.gather(...)`. Explicit `as_of_date` requests continue to skip the latest-business-date
lookup and use the caller-provided date.

Added focused coverage proving portfolio and default-date reads start concurrently, and that
explicit-date requests do not call the default-date lookup.

## Impact

This reduces `CashBalances` latency for default-date source-data requests while preserving
portfolio validation, no-business-date failure behavior, cash snapshot filtering, cash-account
master fallback behavior, FX conversion, response shape, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused cash-balance service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
