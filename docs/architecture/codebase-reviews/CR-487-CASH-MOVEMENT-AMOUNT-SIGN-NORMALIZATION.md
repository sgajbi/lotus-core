# CR-487: Cash Movement Amount Sign Normalization

Date: 2026-05-28

## Scope

Cost-calculator cash deposit and withdrawal amount handling.

## Finding

The cost-calculator `Transaction` model requires non-negative `gross_transaction_amount` and
`quantity`, but strategy code can still receive mutated in-memory objects, repair/replay records,
or dirty legacy transaction payloads after model construction. Cash movement strategies used the
raw gross amount when present. If a legacy withdrawal carried a signed negative cash amount, the
withdrawal strategy inverted the sign again and produced positive `net_cost_local`/`net_cost`
instead of a cash outflow. A signed deposit could similarly create a negative deposit lot.

For banking-grade cash cost-basis and cash-position calculations, the cash movement amount should
be normalized as a magnitude. Direction belongs in the transaction strategy: deposits add cash,
withdrawals remove cash.

## Change

Hardened `_cash_movement_amount(...)` to return the absolute value of the selected movement basis:

1. use `gross_transaction_amount` when present and non-zero,
2. fall back to `quantity` when gross amount is zero,
3. normalize the selected amount to a positive magnitude before strategy sign application.

Added regression coverage for post-construction signed legacy cash amounts in both deposit and
withdrawal strategies.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
4. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused cost-calculator proof: `47 passed`
2. Cost-calculator unit pack: `111 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2350 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Cash
movement cost calculations now preserve deposit/outflow direction even when legacy or repaired
objects carry signed cash movement amounts.
