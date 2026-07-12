# CR-697: Transaction Ledger Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService.get_transactions(...)` validated portfolio existence before reading the latest
business date for default-date, non-projected ledger requests. Those scope reads are independent,
so paginated transaction ledger requests serialized setup before running the transaction count and
page/evidence reads.

## Change

Default-date, non-projected transaction ledger requests now resolve portfolio existence and the
latest business date with `asyncio.gather(...)`. Explicit `as_of_date` requests and projected
ledger requests continue to skip the latest-business-date lookup.

Added focused coverage proving portfolio-existence and default-date reads start concurrently, and
that explicit-date requests do not call the default-date lookup.

## Impact

This reduces `TransactionLedgerWindow` latency for default-date source-data requests while
preserving portfolio validation, projected-ledger behavior, explicit-date behavior, transaction
count/page/evidence concurrency, reporting-currency enrichment, response shape, database schema,
wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused transaction-service ledger proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
