# CR-350 Position Valuation FX Guardrails

Date: 2026-05-27

## Scope

Reviewed core position valuation math for currency normalization and FX-rate guardrails.

## Findings

`ValuationLogic.calculate_valuation(...)` assumed currency codes arrived in canonical uppercase form
and only converted `quantity` defensively to `Decimal`. That left two banking-grade correctness
risks in the calculator boundary:

1. lower-case or padded currency codes could incorrectly trigger a missing-FX path even when the
   price, instrument, and portfolio currencies were actually the same,
2. zero or negative FX rates could be applied directly to market value, producing false valuations
   instead of failing closed.

The calculator also accepted `Decimal`-typed inputs but was not robust when callers supplied
float-like numeric values at the boundary.

## Actions Taken

Hardened `src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py`:

1. normalize price, instrument, and portfolio currency codes before comparison,
2. convert market price, cost basis values, quantity, and supplied FX rates through one `Decimal`
   conversion helper,
3. reject missing, zero, and negative FX rates through a shared positive-rate guard before valuation
   math runs,
4. preserve existing fail-closed behavior by returning `None` when valuation cannot be trusted.

Added direct unit proof for:

1. currency-code normalization before FX requirement checks,
2. float-like numeric inputs without binary float arithmetic,
3. zero FX rejection,
4. negative price-alignment FX rejection.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py -q
14 passed

python -m pytest tests/unit/services/calculators/position_valuation_calculator -q
29 passed

python -m ruff check src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py
All checks passed
```

## Follow-Up

No API or wiki source change is required for this slice because the public calculator contract still
returns the same tuple on trusted valuation inputs and `None` when valuation inputs are not
supportable. Continue hardening calculation paths around deterministic `Decimal` policy, data-quality
fences, stale/missing market-data handling, and persisted valuation evidence.
