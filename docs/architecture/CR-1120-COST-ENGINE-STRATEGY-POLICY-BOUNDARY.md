# CR-1120 Cost Engine Strategy Policy Boundary

Date: 2026-06-21

## Scope

Cost calculator engine strategy policy in
`src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`.

## Finding

The cost engine still concentrated BUY, SELL, DIVIDEND, INTEREST, and FX validation policy inside
strategy methods. The module was already behavior-rich and tested, but Radon still reported the
core strategy methods/classes as B/C-ranked complexity:

- `SellStrategy.calculate_costs`: `C (14)`
- `BuyStrategy.calculate_costs`: `C (13)`
- `InterestStrategy.calculate_costs`: `C (11)`
- `DividendStrategy.calculate_costs`: `B (9)`
- `CostCalculator._validate_fx`: `B (8)`

This made a critical calculation module harder to review and raised the risk of future changes
mixing cost-field assignment, invariant validation, lot mutation, FX validation, and income-flow
policy in one method.

## Action Taken

Extracted focused helpers for:

- common zero-cost and realized-P&L field assignment,
- BUY cost-field assignment and invariant validation,
- SELL proceeds validation, lot availability policy, cost-basis consumption, and disposal field
  assignment,
- DIVIDEND and INTEREST zero-quantity/zero-price and zero-cost invariants,
- INTEREST direction normalization,
- transaction currency and FX-rate validation.

The public calculator API, strategy selection, transaction mutation semantics, error messages, and
lot-disposition integration remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\engine\test_cost_calculator.py tests\unit\services\calculators\cost_calculator_service\engine\test_cost_basis_strategies.py -q`
- Result: `72 passed`

Focused static proof:

- `python -m ruff check src\services\calculators\cost_calculator_service\app\cost_engine\processing\cost_calculator.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\calculators\cost_calculator_service\app\cost_engine\processing\cost_calculator.py -s --min B`
- Result: no B-or-worse functions/classes reported

Measured movement:

- `SellStrategy.calculate_costs`: `C (14)` -> `A (4)`
- `BuyStrategy.calculate_costs`: `C (13)` -> `A (2)`
- `InterestStrategy.calculate_costs`: `C (11)` -> `A (4)`
- `DividendStrategy.calculate_costs`: `B (9)` -> `A (3)`
- `CostCalculator._validate_fx`: `B (8)` -> `A (2)`

## Residual Risk

The module still reports B-ranked maintainability (`B (16.31)`) because it remains a large
calculation module with many strategy classes and helper policies. The next cost-engine slice
should consider moving the newly named helper policies into a cohesive strategy-policy module only
after broader cost-calculator tests confirm there is no import or package-layout risk.

## Bank-Buyable Control Movement

This slice improves:

- architecture and module boundaries,
- deterministic data/methodology quality for cost and realized-P&L calculations,
- meaningful domain test coverage for behavior-preserving refactoring.

It does not claim full bank-buyable readiness for `lotus-core`.
