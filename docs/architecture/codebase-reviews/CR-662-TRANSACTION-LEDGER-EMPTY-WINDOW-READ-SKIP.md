# CR-662: Transaction Ledger Empty Window Read Skip

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService.get_transactions(...)` always issued the paged transaction read after the
filtered ledger count query. When the count query returned zero, the service still executed the
joined transaction/cost/cashflow page query even though the response was already known to be empty.

For filtered transaction-ledger windows and source-data product reads, this added an avoidable
database round trip on empty result sets.

## Change

Short-circuited empty transaction-ledger windows after the count query:

1. when `total_count == 0`, the service now returns an empty transaction page without calling
   `get_transactions(...)`,
2. latest evidence timestamp remains `None` for empty windows,
3. non-empty complete first pages still derive evidence timestamps from returned rows,
4. partial, skipped, or paged windows still use the repository latest-evidence query.

Updated transaction service tests to prove the empty-window path skips both the page read and the
latest-evidence query.

## Impact

This removes an unnecessary joined transaction read from empty `TransactionLedgerWindow` requests
while preserving response shape, pagination metadata, data-quality classification, evidence
metadata semantics, reporting-currency behavior, database schema, OpenAPI contracts, and wiki
source.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
