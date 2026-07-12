# CR-684: Cash Balance Parallel Account Record Builds

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashBalanceResolver.build_cash_account_balance_records(...)` built each master-backed and
fallback-backed cash account record sequentially. Each record build performs an independent
portfolio-to-reporting-currency conversion after master rows and fallback account IDs have been
resolved. The final response already sorts records deterministically, so sequential construction
was adding avoidable latency without providing ordering value.

## Change

The resolver now plans all master-backed and fallback-backed account-record inputs first, preserves
duplicate account suppression while planning, builds all account records with `asyncio.gather(...)`,
and retains the existing deterministic sort by account currency and cash account ID.

Added service coverage that would deadlock under sequential execution, proving master-backed and
fallback-backed account balance conversions are started concurrently.

## Impact

This reduces `HoldingsAsOf` cash-balance and portfolio-summary cash-enrichment latency for
multi-account portfolios while preserving master-row precedence, fallback account ID recovery,
duplicate suppression, final ordering, reporting-currency conversion behavior, response shape,
database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused cash-balance service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
