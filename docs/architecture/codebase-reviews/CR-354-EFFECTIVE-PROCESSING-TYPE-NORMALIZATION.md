# CR-354 Effective Processing Type Normalization

Date: 2026-05-27

## Scope

Reviewed shared transaction processing type resolution used by position and cashflow calculators.

## Findings

`resolve_effective_processing_transaction_type(...)` uppercased `transaction_type` and
`component_type` without trimming source-system whitespace. Lower-case or padded source values could
therefore fail to match the canonical calculator branch.

For example, a source event with transaction type `" buy "` could bypass the `BUY` branch in the
position calculator, leaving quantity and cost basis unchanged even though the calculation math
itself was correct.

## Actions Taken

Hardened
`src/libs/portfolio-common/portfolio_common/transaction_domain/effective_processing_type.py`:

1. added shared processing-type normalization with `strip().upper()`,
2. applied it to FX component processing type resolution,
3. applied it to fallback transaction type resolution.

Added direct shared-library tests for normalized transaction type and FX component type values, plus
a position-calculator test proving a padded lower-case `BUY` event reaches the correct calculation
branch.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/libs/portfolio_common/test_effective_processing_type.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q
48 passed

python -m pytest tests/unit/libs/portfolio_common/test_effective_processing_type.py tests/unit/libs/portfolio_common/test_fx_validation.py tests/unit/libs/portfolio_common/test_fx_linkage.py tests/unit/libs/portfolio_common/test_fx_contract_instrument.py -q
24 passed

python -m pytest tests/unit/services/calculators/position_calculator -q
55 passed

python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/effective_processing_type.py tests/unit/libs/portfolio_common/test_effective_processing_type.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this canonicalizes internal transaction-domain
processing values. Continue reviewing transaction-domain helpers that still use raw `.upper()` so
source vocabulary normalization is consistent across validation, linkage, cost, cashflow, and
position calculation paths.
