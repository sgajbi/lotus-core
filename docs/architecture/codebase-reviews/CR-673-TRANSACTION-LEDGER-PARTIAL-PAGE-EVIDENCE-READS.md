# CR-673: Transaction Ledger Partial-Page Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService.get_transactions(...)` already skips page and evidence reads for empty ledger
windows and derives the evidence timestamp from complete first-page windows. For known partial or
skipped pages, however, it still read the transaction page before starting the whole-window latest
evidence timestamp query even though both reads are independent after the count query resolves.

## Change

The service now reads the transaction page and latest evidence timestamp concurrently for known
partial windows (`skip > 0` or `limit < total_count`). Empty windows still short-circuit, and
complete first-page windows still derive the timestamp from returned rows with the existing
defensive fallback if fewer rows are returned than the count predicted.

Added service coverage that would deadlock under sequential execution, proving the partial-page
page and evidence reads are started concurrently.

## Impact

This reduces `TransactionLedgerWindow:v1` latency for paginated ledger reads while preserving empty
window behavior, complete-window timestamp derivation, pagination metadata, reporting-currency
restatement, response contracts, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused transaction service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
