# CR-845: Transaction Ledger Response Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_transactions(...)` still assembled `PaginatedTransactionResponse` inline
after transaction ledger date policy, filter construction, read orchestration, record mapping, and
reporting-currency enrichment had been separated.

That response policy includes TransactionLedgerWindow product identity, runtime as-of date fallback,
data-quality classification, pagination metadata, reporting-currency propagation, and evidence
timestamp propagation. It should be directly tested outside service orchestration.

## Change

Added `paginated_transaction_ledger_response(...)` to `transaction_records.py`.

`TransactionService` now delegates transaction ledger response construction to that helper. Direct
record/response tests prove complete-window metadata, partial-window classification, empty-window
classification, effective as-of date precedence, end-date fallback, and current-date fallback.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction ledger repository predicates,
3. pagination or sorting semantics,
4. reporting-currency conversion semantics,
5. source-data-product runtime metadata semantics,
6. data-quality classification values,
7. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service response-assembly
modularity hardening and does not change operator workflow, supported feature behavior, API usage,
or runtime commands.

## Validation

Local validation passed for the slice:

1. focused transaction record/response and service tests,
2. focused transaction service, date, metadata, realized-tax, reporting-currency, read, record, FX,
   and portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
