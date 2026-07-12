# CR-616: Cash Position Delta Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The position calculator cash-position delta path still converted gross amount, quantity, booked
base cost, and booked local cost inline with `Decimal(str(...))`. For cash portfolio flows, the
booked cost values were converted again during zero-fallback checks, adding avoidable duplicate
work in a core position calculation path.

## Change

Routed cash-position amount and optional booked-cost normalization through
`portfolio_common.decimal_amounts.required_decimal(...)`, normalized booked cost values once, and
kept the existing quantity fallback behavior for zero booked costs on cash-flow transactions.

## Impact

This reduces duplicate conversion work and keeps cash-position delta normalization aligned with the
shared portfolio-common decimal helper while preserving quantity, base cost, local cost, adjustment,
cash in/out, and FX settlement semantics. API route shape, response fields, OpenAPI contracts,
database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `python scripts/warning_budget_gate.py --suite unit --max-warnings 0 --quiet`
7. `git diff --check`
