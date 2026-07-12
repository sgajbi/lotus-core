# CR-837: Realized Tax Reporting Currency Total Boundary

Status: Hardened on 2026-06-02.

## Finding

`TransactionService.get_realized_tax_summary(...)` still owned the loop that converted realized-tax
currency buckets into a single requested reporting-currency total.

That calculation belongs with the `PortfolioRealizedTaxSummary` aggregation policy rather than the
service orchestration layer.

## Change

Added `realized_tax_reporting_currency_total(...)` to `transaction_realized_tax.py`.

The service now delegates reporting-currency total calculation to that helper while still supplying
its existing FX conversion boundary. Direct helper coverage proves conversion sequencing and the
`None` result when no reporting currency is requested; service coverage proves the orchestration
passes currency totals, reporting currency, effective as-of date, and conversion boundary.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. realized-tax transaction filters,
3. realized-tax currency bucket aggregation,
4. FX conversion behavior,
5. metadata and data-quality behavior,
6. database schema or migrations.

## No Wiki Change

No wiki source update is required. The change is internal query-service aggregation modularity
hardening and does not change operator workflow, supported feature behavior, API usage, or runtime
commands.

## Validation

Local validation passed for the slice:

1. focused transaction service, metadata, realized-tax, reporting-currency, and portfolio validation tests,
2. Alembic head check,
3. migration SQL contract smoke,
4. ruff check and format check,
5. git diff whitespace checks.
