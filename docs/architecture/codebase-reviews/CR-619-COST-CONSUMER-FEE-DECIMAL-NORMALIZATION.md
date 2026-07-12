# CR-619: Cost Consumer Fee Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The cost-calculator consumer still normalized incoming `trade_fee` and fee component fields with
local `Decimal(str(...))` calls before building the engine fee payload. This duplicated the shared
transaction-fee component resolver's numeric handling and left fee normalization less consistent
than the downstream cost engine.

## Change

Added a local zero-default fee amount normalizer backed by
`portfolio_common.decimal_amounts.decimal_or_none(...)`, normalized `trade_fee` and fee components
once, and passed Decimals into `resolve_transaction_trade_fee(...)` for the existing precedence and
non-negative validation contract.

## Impact

This keeps cost-consumer fee transformation aligned with shared portfolio-common decimal handling
while preserving component precedence over `trade_fee`, blank component values as zero, and
existing invalid/negative fee failures. API route shape, response fields, OpenAPI contracts,
database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal consumer calculation-path reuse with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/libs/portfolio-common/test_transaction_fee_components.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
