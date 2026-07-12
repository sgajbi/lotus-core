# CR-1030: Cashflow Amount Policy Boundary

Date: 2026-06-05

## Scope

Reduce cashflow calculation complexity while preserving trade-fee resolution, interest deduction
handling, net-interest override behavior, BUY/FEE amount treatment, SELL/dividend amount treatment,
interest direction signs, FX signs, adjustment movement signs, transfer in/out signs, quantity
fallback signs, cashflow object construction, metrics, logging, and epoch behavior.

## Finding

`CashflowLogic.calculate` mixed transaction-type normalization, trade-fee resolution, interest
deduction math, base amount calculation, classification sign policy, adjustment/transfer special
cases, `Cashflow` construction, Prometheus metrics, and logging in one C-ranked method.

## Action

Extracted focused helpers for base cashflow amount calculation, interest amount calculation,
classification/direction sign application, interest sign policy, adjustment sign policy, and
transfer sign policy. The public calculator method remains the object-construction, metric, and
logging boundary.

## Result

`CashflowLogic.calculate` improved from `C (18)` to `A (2)`, and `cashflow_logic.py` remains
A-ranked maintainability at `A (52.17)`. Follow-up remains to reduce `_signed_cashflow_amount`
`B (7)` when it is the next best cashflow-domain slice.

## Evidence

- `python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py -q`
  => 35 passed
- `python -m ruff check src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py -s`
  => `CashflowLogic.calculate` `A (2)`
- `python -m radon mi src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py -s`
  => `cashflow_logic.py` `A (52.17)`
- `python -m radon raw src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py`
  => 149 SLOC / 76 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cashflow calculation refactor that preserves
existing amount, sign, metrics, and logging semantics.
