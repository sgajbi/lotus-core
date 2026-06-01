# CR-620: Transaction Event Amount Guard Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionEvent` non-negative and positive amount validators still used local `Decimal(str(...))`
conversion even after shared decimal normalization was introduced. These validators protect common
transaction event fields used by ingestion, cost, position, valuation, FX, and synthetic-flow paths.

## Change

Added a small event-local decimal guard backed by
`portfolio_common.decimal_amounts.decimal_or_none(...)` and routed the non-negative and positive
transaction amount validators through it. Added focused coverage for string amount inputs across
core transaction and FX amount fields.

## Impact

This aligns transaction-event numeric guardrails with shared portfolio-common decimal handling while
preserving the existing non-negative and strictly-positive validation messages. API route shape,
response fields, OpenAPI contracts, database schema, wiki source, and platform contracts are
unchanged.

No wiki update was needed because this is internal event-validation reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_portfolio_common_decimal_amounts.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/libs/portfolio-common/test_events.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
