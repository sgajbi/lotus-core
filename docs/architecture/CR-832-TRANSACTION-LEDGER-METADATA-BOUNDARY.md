# CR-832: Transaction Ledger Metadata Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService` still owned reusable transaction-ledger metadata policy inline:

1. data-quality classification for complete, partial, and empty ledger windows,
2. latest transaction evidence timestamp selection from returned source rows.

Those rules are product metadata policy for `TransactionLedgerWindow` and related transaction-derived
products, not service orchestration concerns.

## Change

Created `transaction_metadata.py` and moved the ledger metadata helpers into that module:

1. `ledger_data_quality_status(...)`,
2. `latest_transaction_evidence_timestamp(...)`.

`TransactionService` now calls the helper functions for transaction ledger responses and realized
tax summary metadata.

Focused helper tests now live in `test_transaction_metadata.py`; service tests continue to prove the
public response behavior through `get_transactions(...)` and `get_realized_tax_summary(...)`.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction filters or repository methods,
3. reporting-currency conversion behavior,
4. realized tax summary aggregation,
5. database schema or migrations,
6. OpenAPI or route-family metadata.

## No Wiki Change

No wiki source update is required. The change is internal query-service metadata modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction service and transaction metadata tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
