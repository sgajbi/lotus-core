# CR-1162 Cost BUY Lot Repository Boundary

Date: 2026-06-22

## Scope

- `src/services/calculators/cost_calculator_service/app/repository.py`
- `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py`

## Finding

`CostCalculatorRepository.upsert_buy_lot_state(...)` mixed BUY lot identity construction, mutable lot
economics, accrued-interest defaulting, source metadata extraction, PostgreSQL conflict-update field
selection, and database execution in one B-ranked persistence method.

The method is part of Core-owned cost-basis and tax-lot state persistence. Keeping payload policy and
conflict-update policy inline made the durable lot-state path harder to review and easier to regress.

## Action

Extracted focused helpers for:

- deterministic BUY lot payload construction,
- PostgreSQL excluded-field update selection for immutable identity fields.

Added DB-backed integration coverage proving an existing lot row is updated idempotently while
`lot_id` and `source_transaction_id` remain immutable and mutable economics/metadata are refreshed
from the latest engine output.

## Measured Signal

- Before: `CostCalculatorRepository.upsert_buy_lot_state(...)` was `B (6)`.
- After: `CostCalculatorRepository.upsert_buy_lot_state(...)` is `A (1)`.
- New helper functions are A-ranked by cyclomatic complexity.

## Validation

- `python -m pytest tests\integration\services\calculators\cost_calculator_service\test_int_cost_repository_lot_offset.py -q`
  - `4 passed`
- `python -m ruff check src\services\calculators\cost_calculator_service\app\repository.py tests\integration\services\calculators\cost_calculator_service\test_int_cost_repository_lot_offset.py`
  - passed
- `python -m ruff format --check src\services\calculators\cost_calculator_service\app\repository.py tests\integration\services\calculators\cost_calculator_service\test_int_cost_repository_lot_offset.py`
  - passed
- `python -m radon cc -s src\services\calculators\cost_calculator_service\app\repository.py`
  - target method is A-ranked

## Residual Risk

Cost repository complexity is now concentrated in lower-ranked helpers and the broader cost engine,
consumer idempotency, database constraints, and transaction-contract coverage. This slice does not
change public APIs, source-data contracts, OpenAPI, or wiki-facing operator behavior.
