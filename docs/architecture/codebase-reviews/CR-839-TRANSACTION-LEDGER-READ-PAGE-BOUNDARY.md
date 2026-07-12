# CR-839: Transaction Ledger Read Page Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_transactions(...)` still owned transaction ledger count, page-read, and
latest-evidence timestamp policy inline after repository filter construction had been extracted.

That read-window policy decides when an empty ledger should avoid page/evidence reads, when a full
page can derive evidence from returned rows, and when a partial or short page must ask the repository
for global latest evidence. It should be explicit and directly tested outside public response
assembly.

## Change

Created `transaction_reads.py` with:

1. `TransactionLedgerPage`,
2. `read_transaction_ledger_page(...)`.

`TransactionService` now delegates transaction ledger read-window orchestration to that helper and
continues to own DTO mapping, reporting-currency enrichment, and source-data-product response
assembly. Focused helper tests prove empty-window, complete-window, partial-window, and short-page
evidence behavior.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. repository method names,
3. repository filter values,
4. pagination, sorting, or latest-evidence behavior,
5. reporting-currency enrichment,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service read-orchestration
modularity hardening and does not change operator workflow, supported feature behavior, API usage,
or runtime commands.

## Validation

Local validation passed for the slice:

1. focused transaction read helper and service tests,
2. focused transaction service, metadata, realized-tax, reporting-currency, and portfolio validation
   tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
