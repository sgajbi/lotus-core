# CR-615: Transaction Fee Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The shared transaction fee component resolver still converted explicit trade fees and component
amounts inline with `Decimal(str(...))` and lacked focused unit coverage. This helper feeds
booking, ingestion, cashflow, and cost-calculation paths, so duplicated conversion and weak proof
increase drift risk for transaction cost evidence.

## Change

Routed fee amount normalization through `portfolio_common.decimal_amounts`, added explicit
numeric-validation errors for malformed fee evidence, preserved blank or missing component values
as zero, and added focused unit coverage for explicit fees, component summing, negative values, and
invalid values.

## Impact

This keeps transaction fee normalization consistent with valuation price/rate normalization while
preserving existing precedence and non-negative constraints. API route shape, response fields,
OpenAPI contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_decimal_amounts.py tests/unit/libs/portfolio-common/test_transaction_fee_components.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
