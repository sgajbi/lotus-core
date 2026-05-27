# CR-353 Cost Calculator Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed the cost calculator boundary for source-system vocabulary variation in currency codes and
transaction types.

## Findings

`CostCalculator` compared `trade_currency` and `portfolio_base_currency` directly and resolved
strategies from the raw transaction type value. That left two calculation reliability risks:

1. same-currency transactions with lower-case or padded currency codes could be treated as
   cross-currency and rejected for missing FX,
2. transaction types with lower-case or padded source values could be rejected as unknown instead of
   resolving to the canonical strategy.

For banking feeds, these are common source-system normalization issues and should be handled before
calculation policy is applied.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`:

1. normalized trade and portfolio-base currency codes before FX validation,
2. defaulted same-currency transactions to FX rate `1` after normalization,
3. normalized transaction type before strategy lookup while preserving enum inputs.

Added direct unit proof for:

1. same-currency code normalization before FX requirement checks,
2. lower-case/padded transaction type normalization before strategy resolution.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q
40 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
89 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this slice canonicalizes calculator inputs at the
existing cost-engine boundary. Continue reviewing upstream parser and consumer enrichment paths for
the same normalization posture so source vocabulary is corrected as early as practical.
