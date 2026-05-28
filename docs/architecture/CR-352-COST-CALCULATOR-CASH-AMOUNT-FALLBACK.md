# CR-352 Cost Calculator Cash Amount Fallback

Date: 2026-05-27

## Scope

Reviewed cash inflow and outflow cost calculation for source-system amount-field variation.

## Findings

After CR-351 hardened position updates, the cost calculator still derived cash inflow and outflow
amounts only from `gross_transaction_amount`. Bank source feeds may carry cash balance movement in
`quantity` while booking gross amount as zero.

That could make the cost-processed event carry zero book cost for a real cash movement, leaving cost
evidence inconsistent with corrected position movement and weakening downstream valuation,
reconciliation, and auditability.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`
with a shared cash movement amount helper:

1. use `gross_transaction_amount` when it is non-zero,
2. otherwise use `quantity` as the cash movement amount.

Applied the helper to:

1. `CashInflowStrategy`, including the synthetic cash lot quantity,
2. `CashOutflowStrategy`, including local and base net cost.

Added direct unit proof for quantity-backed deposit and withdrawal events where
`gross_transaction_amount` is zero.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q
38 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
87 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py
All checks passed
```

Additional note:

```text
python -m ruff check src/services/calculators/cost_calculator_service tests/unit/services/calculators/cost_calculator_service
```

found existing import-format and line-length debt in neighboring cost-calculator consumer and
repository files outside this slice. The touched calculation files passed Ruff.

## Follow-Up

No API or wiki source change is required for this slice because it aligns internal cost-event
calculation with existing cash-position semantics. Follow-up hygiene can normalize the broader
cost-calculator package Ruff debt separately if it becomes part of the current hardening batch.
