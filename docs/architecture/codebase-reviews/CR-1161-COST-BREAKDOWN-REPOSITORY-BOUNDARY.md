# CR-1161 Cost Breakdown Repository Boundary

Date: 2026-06-22

## Scope

- `src/services/calculators/cost_calculator_service/app/repository.py`
- `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py`

## Finding

`CostCalculatorRepository.replace_transaction_cost_breakdown(...)` mixed transaction lookup,
idempotent stale-row deletion, fee-component selection, zero-fee filtering, currency selection, and
`TransactionCost` row construction in one B-ranked persistence method.

That method is part of the cost-calculation persistence path, so readability and focused regression
coverage matter for fee, tax, cost-basis, and downstream `TransactionCostCurve` evidence.

## Action

Extracted focused helpers for:

- positive fee-component selection,
- deterministic `TransactionCost` row construction with the persisted transaction currency.

The public repository method now coordinates transaction lookup, idempotent replacement, and row
persistence while preserving existing behavior.

## Measured Signal

- Before: `CostCalculatorRepository.replace_transaction_cost_breakdown(...)` was `B (7)`.
- After: `CostCalculatorRepository.replace_transaction_cost_breakdown(...)` is `A (2)`.
- New helper functions are A-ranked by cyclomatic complexity.

## Validation

- `python -m pytest tests\integration\services\calculators\cost_calculator_service\test_int_cost_repository_lot_offset.py -q`
  - `3 passed`
- `python -m ruff check src\services\calculators\cost_calculator_service\app\repository.py tests\integration\services\calculators\cost_calculator_service\test_int_cost_repository_lot_offset.py`
  - passed
- `python -m ruff format --check src\services\calculators\cost_calculator_service\app\repository.py tests\integration\services\calculators\cost_calculator_service\test_int_cost_repository_lot_offset.py`
  - passed
- `python -m radon cc -s src\services\calculators\cost_calculator_service\app\repository.py`
  - target method is A-ranked

## Residual Risk

`CostCalculatorRepository.upsert_buy_lot_state(...)` remains B-ranked and can be reviewed as a
separate persistence-boundary slice. Broader cost-calculation correctness still depends on the
calculator engine, consumer idempotency, database constraints, and transaction-contract coverage.
