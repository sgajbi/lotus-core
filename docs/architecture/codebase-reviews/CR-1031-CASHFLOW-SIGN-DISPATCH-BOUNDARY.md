# CR-1031: Cashflow Sign Dispatch Boundary

Date: 2026-06-05

## Scope

Reduce cashflow sign-dispatch complexity while preserving interest direction signs, FX buy/sell
signs, adjustment movement signs, transfer in/out signs, quantity fallback signs, and default
outflow signs.

## Finding

After CR-1030, `_signed_cashflow_amount` still mixed special transaction-type dispatch with direct
classification sign decisions and default outflow behavior in one B-ranked helper.

## Action

Added an explicit classification sign-factor map and a focused classification sign helper. Interest,
adjustment, and transfer policies remain in their dedicated helpers, while direct classification
sign behavior is table-driven.

## Result

`_signed_cashflow_amount` improved from `B (7)` to `A (4)`. Every function/class/method in
`cashflow_logic.py` now reports A-ranked cyclomatic complexity, and the module remains A-ranked
maintainability at `A (52.93)`.

## Evidence

- `python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py -q`
  => 35 passed
- `python -m ruff check src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py -s`
  => `_signed_cashflow_amount` `A (4)` and every function/class/method A-ranked
- `python -m radon mi src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py -s`
  => `cashflow_logic.py` `A (52.93)`
- `python -m radon raw src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py`
  => 147 SLOC / 74 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cashflow calculation refactor that preserves
existing cashflow sign semantics.
