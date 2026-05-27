# CR-351 Cash Position Amount Fallback

Date: 2026-05-27

## Scope

Reviewed cash-position movement calculation for source-system amount-field variation.

## Findings

`PositionCalculator._cash_position_amount_delta(...)` derived cash balance movement only from
`gross_transaction_amount`. That is correct for the canonical Lotus feed, but it leaves a reliability
gap for bank source feeds that carry cash movement amount in `quantity` while booking
`gross_transaction_amount` as zero.

For cash instruments, `quantity` is the balance unit. Dropping a non-zero quantity movement because
gross amount is zero can silently understate or overstate cash balances, cost basis, downstream
valuation readiness, and portfolio-level aggregation.

## Actions Taken

Hardened `src/services/calculators/position_calculator/app/core/position_logic.py` so cash movement
amount calculation uses:

1. absolute `gross_transaction_amount` when it is non-zero,
2. otherwise absolute `quantity` as the cash-amount fallback.

Existing transaction-type direction still controls whether the movement is an inflow or outflow, so
withdrawals, fees, and taxes continue to reduce cash positions while deposits increase them.

Added direct unit proof for deposit, withdrawal, fee, and tax cash flows where
`gross_transaction_amount` is zero and the movement amount is supplied by `quantity`.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q
43 passed

python -m pytest tests/unit/services/calculators/position_calculator -q
54 passed

python -m ruff check src/services/calculators/position_calculator/app/core/position_logic.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py
All checks passed
```

## Follow-Up

No API or wiki source change is required for this slice because this is a deterministic calculator
fallback inside the existing cash-position contract. Continue reviewing calculation paths for
source-field variation, signed amount conventions, idempotent replay behavior, and persisted
evidence that proves downstream valuation and aggregation are recalculated from corrected positions.
