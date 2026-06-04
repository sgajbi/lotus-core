# CR-842: Realized Tax Summary Response Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_realized_tax_summary(...)` still assembled
`PortfolioRealizedTaxSummaryResponse` inline after realized-tax evidence reads, currency-bucket
aggregation, and reporting-currency total calculation had been separated.

That response policy includes tax-evidence transaction count, reason-code selection, source-data
product runtime metadata, data-quality classification, and evidence timestamp propagation. It is
realized-tax summary output policy and should be directly tested outside service orchestration.

## Change

Added `portfolio_realized_tax_summary_response(...)` to `transaction_realized_tax.py`.

`TransactionService` now delegates realized-tax summary DTO construction to that helper. Direct
realized-tax tests prove ready and empty-evidence response behavior, including product identity,
runtime as-of date, data-quality status, evidence timestamp propagation, tax-evidence transaction
count, reason codes, and reporting-currency total preservation.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. realized-tax summary repository predicates,
3. source transaction count semantics,
4. tax-evidence transaction count semantics,
5. reason-code values,
6. source-data-product runtime metadata semantics,
7. reporting-currency conversion semantics,
8. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service response-assembly
modularity hardening and does not change operator workflow, supported feature behavior, API usage,
or runtime commands.

## Validation

Local validation passed for the slice:

1. focused realized-tax helper and service tests,
2. focused transaction service, metadata, realized-tax, reporting-currency, read, record, and
   portfolio validation tests,
3. Alembic head check,
4. migration SQL contract smoke,
5. ruff check and format check,
6. git diff whitespace checks.
