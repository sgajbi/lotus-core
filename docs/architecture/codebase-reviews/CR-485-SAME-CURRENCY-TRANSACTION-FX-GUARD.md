# CR-485: Same-Currency Transaction FX Guard

Date: 2026-05-28

## Scope

Cost-calculator FX-rate validation for same-currency transactions.

## Finding

The cost calculator correctly defaulted missing same-currency transaction FX rates to `1`, and it
rejected missing/non-positive FX rates for cross-currency transactions. It did not fail closed when
a same-currency transaction carried an explicitly non-positive `transaction_fx_rate` after model
construction. That could happen through internal mutation, repair/replay paths, or dirty historical
objects and would allow downstream cost strategies to multiply costs by an invalid FX rate.

For banking-grade cost-basis calculation, an explicitly supplied non-positive FX rate is invalid
regardless of whether the transaction and portfolio currencies match.

## Change

Hardened `CostCalculator._validate_fx(...)` so it:

1. normalizes any supplied `transaction_fx_rate` to `Decimal`,
2. rejects invalid, zero, or negative supplied FX rates before strategy execution,
3. still defaults missing same-currency FX rates to `1`,
4. preserves the existing cross-currency missing-rate failure behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
4. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused cost-calculator proof: `45 passed`
2. Cost-calculator unit pack: `109 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2347 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
cost-calculator read/processing boundary now rejects explicitly invalid same-currency FX rates
instead of allowing distorted cost and realized P&L calculations.
