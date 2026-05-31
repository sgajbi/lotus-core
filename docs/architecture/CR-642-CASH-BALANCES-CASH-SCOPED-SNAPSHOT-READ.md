# CR-642: Cash Balances Cash-Scoped Snapshot Read

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`HoldingsAsOf:v1` cash-balance reads used the shared latest-snapshot repository query for the full
portfolio and filtered cash instruments in Python. Large portfolios therefore transferred and
assembled non-cash holdings for a cash-only endpoint.

## Change

Added an optional instrument asset-class predicate to the reporting repository's latest snapshot
query and routed cash-balance reads through `instrument_asset_class="CASH"`. The cash-balance
resolver still keeps the existing Python cash-row guard as a defensive response boundary.

## Impact

This reduces row transfer and DTO assembly for cash-balance API reads on broad portfolios while
preserving as-of snapshot semantics, current-epoch/open-position filtering, master-account zero
balance rows, FX conversion behavior, latest evidence timestamp handling, and response shape.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal query-scope hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
