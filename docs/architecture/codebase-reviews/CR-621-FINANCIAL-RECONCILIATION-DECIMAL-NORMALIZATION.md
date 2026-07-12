# CR-621: Financial Reconciliation Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Financial reconciliation still converted valuation and timeseries amounts with local
`Decimal(str(...))` calls. Those paths sit on reprocessing and reconciliation support workflows and
consume row data that may arrive as `Decimal`, numeric text, blank sparse evidence, or `None`
depending on repository and test seams.

## Change

Routed reconciliation amount normalization through `portfolio_common.decimal_amounts`:

1. authoritative position-timeseries aggregates now use a zero-default helper for sparse amount
   fields,
2. position valuation required quantities and observed values now use explicit required decimal
   guards,
3. portfolio-timeseries aggregate comparison values now use required decimal guards.

Focused tests now prove string amount evidence is normalized for position valuation, sparse
authoritative amount fields default to zero, and aggregate mismatch detection still works when
repository rows expose numeric text.

## Impact

This keeps reconciliation numeric handling aligned with shared valuation, FX, cost, transaction,
and event normalization while preserving existing mismatch detection, invalid market-price behavior,
FX skip behavior, summary counts, and finding shapes.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal reconciliation calculation hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
