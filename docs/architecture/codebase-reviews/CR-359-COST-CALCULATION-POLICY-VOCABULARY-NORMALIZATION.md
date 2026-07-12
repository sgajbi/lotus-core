# CR-359 Cost Calculation Policy Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed remaining cost-calculator policy and direction decision points after transaction type,
cash-instrument, dependency-sorter, and initial-lot replay normalization.

## Findings

`CostCalculator` still compared some source-controlled values without trimming or canonicalizing:

1. `calculation_policy_id` for excluding accrued interest from bond BUY book cost,
2. `calculation_policy_id` for classifying configured oversold SELL policy behavior,
3. `interest_direction` for INTEREST invariant validation.

Padded or lower-case source values could therefore:

1. incorrectly include accrued interest in book cost when the governed policy intended exclusion,
2. classify an oversold SELL as a strict-policy breach instead of the configured-but-unsupported
   oversold policy path,
3. reject a valid INTEREST expense direction as invalid.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`:

1. reused the internal `strip().upper()` code normalizer for policy IDs,
2. normalized accrued-interest exclusion policy checks,
3. normalized oversold policy checks,
4. normalized interest direction validation.

Added direct unit proof for:

1. padded lower-case accrued-interest exclusion policy preserving book cost without accrued
   interest,
2. padded lower-case oversold policy reaching the configured-but-unsupported policy error path,
3. padded lower-case INTEREST expense direction passing invariant validation.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q
44 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
97 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this hardens internal calculator policy handling
without changing public contracts. Continue reviewing consumer enrichment so source-controlled
policy identifiers are canonicalized before calculation while preserving defensive checks in the
core engine.
