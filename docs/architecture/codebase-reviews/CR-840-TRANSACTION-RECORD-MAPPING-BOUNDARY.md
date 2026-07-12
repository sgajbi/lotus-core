# CR-840: Transaction Record Mapping Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_transactions(...)` still mapped repository transaction rows into public
`TransactionRecord` DTOs inline after ledger read orchestration was extracted.

That mapping included attached cost rows, optional cashflow attachment, and reporting-currency
enrichment sequencing. Those are reusable transaction-ledger response policies and should be tested
outside service orchestration.

## Change

Created `transaction_records.py` with:

1. `transaction_record_from_row(...)`,
2. `transaction_records_from_rows(...)`.

`TransactionService` now delegates transaction row mapping and reporting-currency enrichment to
that helper module. Direct tests prove cost/cashflow preservation, row-order reporting-currency
enrichment, and skip behavior when reporting-currency context is incomplete. Service tests now prove
the service passes ledger rows, resolved reporting currency, effective as-of date, and the FX
conversion boundary to the mapper.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. transaction ledger repository predicates,
3. pagination or latest-evidence behavior,
4. reporting-currency conversion semantics,
5. cashflow or cost response shape,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service response-mapping modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction record helper and service tests,
2. focused transaction service, metadata, realized-tax, reporting-currency, read, record, and
   portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
