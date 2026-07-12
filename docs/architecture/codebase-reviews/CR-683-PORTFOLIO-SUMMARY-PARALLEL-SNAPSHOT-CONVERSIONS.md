# CR-683: Portfolio Summary Parallel Snapshot Conversions

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`ReportingService.get_portfolio_summary(...)` converted each latest snapshot row into reporting
currency sequentially while aggregating total portfolio, invested, cash, valued, and unvalued
summary figures. After portfolio, date, reporting currency, and snapshot rows are resolved, those
row-level conversions are independent.

## Change

The service now builds the snapshot native-value row set, resolves all row-level reporting
currency conversions with `asyncio.gather(...)`, and then applies converted values to the existing
portfolio-summary aggregation loop in deterministic row order. Cash-account enrichment remains
owned by `CashBalanceResolver`.

Added service coverage that would deadlock under sequential execution, proving portfolio-summary
snapshot conversions are started concurrently.

## Impact

This reduces `PortfolioSummary` latency for populated portfolios while preserving cash-account
enrichment, valued/unvalued counts, snapshot-date metadata, total and invested calculations,
same-currency conversion behavior, missing-rate failure behavior, response shape, database schema,
wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service portfolio-summary proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
