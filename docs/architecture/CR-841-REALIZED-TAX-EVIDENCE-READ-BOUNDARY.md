# CR-841: Realized Tax Evidence Read Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_realized_tax_summary(...)` still owned realized-tax source transaction count,
tax-evidence row reads, and latest evidence timestamp selection inline.

That read policy is separate from realized-tax currency aggregation, reporting-currency conversion,
and public source-data-product response assembly. Keeping it inline made the service harder to audit
and forced service tests to duplicate repository read-order assertions.

## Change

Added `RealizedTaxEvidenceRead` and `read_realized_tax_evidence(...)` to `transaction_reads.py`.

`TransactionService` now delegates realized-tax evidence read orchestration to that helper and
continues to own base-currency resolution, effective as-of date resolution, aggregation invocation,
reporting-currency total invocation, and response assembly. Direct read-helper tests prove count and
tax-evidence read sequencing, repository filter propagation, latest evidence timestamp selection,
and empty-evidence behavior.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. realized-tax summary repository filter values,
3. source transaction count semantics,
4. tax-evidence transaction count semantics,
5. latest evidence timestamp behavior,
6. reporting-currency conversion semantics,
7. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service read-orchestration
modularity hardening and does not change operator workflow, supported feature behavior, API usage,
or runtime commands.

## Validation

Local validation passed for the slice:

1. focused transaction read helper and service tests,
2. focused transaction service, metadata, realized-tax, reporting-currency, read, record, and
   portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
