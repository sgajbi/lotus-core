# CR-362 Position Adjustment Direction Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed position cash-adjustment calculation after transaction-type and cash-amount fallback
normalization.

## Findings

`PositionCalculator._cash_position_amount_delta(...)` used raw `movement_direction` values for
`ADJUSTMENT` sign handling. It uppercased the source value but did not trim whitespace.

That created a calculation risk for cash positions: a padded value such as `" outflow "` would not
match `OUTFLOW`, so the adjustment would be treated as an inflow. The result could overstate cash
quantity, base cost, and local cost basis.

## Actions Taken

Hardened `src/services/calculators/position_calculator/app/core/position_logic.py`:

1. added a position-local code normalizer using `strip().upper()`,
2. applied it to adjustment `movement_direction` sign handling,
3. preserved existing default behavior where missing direction is treated as `INFLOW`.

Added direct unit proof that a padded lower-case adjustment outflow subtracts from quantity,
`cost_basis`, and `cost_basis_local`.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q
45 passed

python -m pytest tests/unit/services/calculators/position_calculator -q
56 passed

python -m ruff check src/services/calculators/position_calculator/app/core/position_logic.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this hardens internal position calculation without
changing public contracts. Continue reviewing position and cashflow consumer enrichment for source
direction fields that can affect sign handling before calculation.
