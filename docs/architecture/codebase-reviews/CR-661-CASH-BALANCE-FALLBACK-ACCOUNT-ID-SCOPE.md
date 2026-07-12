# CR-661: Cash Balance Fallback Account ID Scope

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashBalanceResolver.build_cash_account_balance_records(...)` always queried
`ReportingRepository.get_latest_cash_account_ids(...)` for every cash security in the response
window. That repository method scans transaction cash-settlement history to recover account IDs for
cash positions that lack an active cash-account master row.

For the normal mastered-account path, the fallback lookup was redundant: active
`cash_account_master` rows already provide the authoritative cash-account identifiers, so querying
transaction history for those same securities added avoidable read work to the cash-balance source
data product.

## Change

Narrowed the fallback transaction lookup to only cash securities not covered by the active
cash-account master rows:

1. normalize cash security IDs once from the cash snapshot rows,
2. build the active master map by normalized `security_id`,
3. call `get_latest_cash_account_ids(...)` only for unmatched cash securities,
4. skip the fallback repository call entirely when all cash securities are master-covered.

Added service coverage for both the fully mastered path and a mixed mastered/unmatched cash account
set.

## Impact

This removes an avoidable transaction-history lookup from mastered cash-balance reads while
preserving legacy transaction-derived account recovery for cash positions without active master
rows. API response shape, totals, source-data runtime metadata, FX behavior, database schema,
OpenAPI contracts, and wiki source are unchanged.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/repositories/test_reporting_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
