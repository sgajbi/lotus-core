# CR-689: Transaction Page Parallel Reporting Enrichment

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService._apply_reporting_currency_fields(...)` already converts money fields within one
transaction concurrently, but `get_transactions(...)` still enriched each transaction page record
sequentially. Multi-row transaction ledger pages therefore serialized independent reporting-currency
enrichment after the page query returned.

## Change

`get_transactions(...)` now builds the response records in page order, collects the requested
reporting-currency enrichment tasks, and resolves those tasks with `asyncio.gather(...)` before
returning the response. The transaction list remains in repository/page order because records are
appended before enrichment tasks run.

Added focused coverage that proves page records must begin reporting-currency enrichment
concurrently.

## Impact

This reduces `TransactionLedgerWindow` latency for paginated reporting-currency requests while
preserving portfolio validation, pagination, sort/filter semantics, evidence timestamp behavior,
cashflow/cost mapping, response shape, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused transaction ledger reporting-enrichment proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
