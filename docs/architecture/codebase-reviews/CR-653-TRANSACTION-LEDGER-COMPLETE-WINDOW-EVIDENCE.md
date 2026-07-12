# CR-653: Transaction Ledger Complete Window Evidence

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionLedgerWindow:v1` fetched a page of ledger rows and the matching source-window count,
then always issued a separate `max(updated_at)` query for runtime metadata. For first-page requests
where the returned row count equals the total matching count, the service already holds every
filtered ledger row and the extra metadata scan is redundant.

## Change

Derived `latest_evidence_timestamp` from returned transaction rows when `skip == 0` and
`len(rows) == total_count`. Partial, skipped, or paginated windows still use the repository
timestamp query so metadata remains scoped to the full filtered ledger window.

## Impact

This removes one database round trip from complete transaction-ledger reads while preserving
partial-window metadata semantics, pagination behavior, reporting-currency restatement, linked
cashflow/cost mapping, data-quality posture, response shape, and product identity.

No route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
