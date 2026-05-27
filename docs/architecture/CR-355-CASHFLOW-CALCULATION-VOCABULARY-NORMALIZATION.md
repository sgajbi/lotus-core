# CR-355 Cashflow Calculation Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed cashflow calculation core logic for source-system vocabulary variation after effective
processing type normalization.

## Findings

`CashflowLogic.calculate(...)` still used raw `transaction.transaction_type`,
`interest_direction`, and `movement_direction` values for amount and sign logic. The consumer can
resolve normalized cashflow rules, but the core calculator could still compute from untrimmed source
values.

That created calculation risks:

1. a padded `BUY` value could use the wrong net amount basis by subtracting fees instead of adding
   them before applying outflow sign,
2. a padded `TRANSFER_OUT` value could miss the explicit transfer-out sign map and fall back to
   quantity direction, turning an outflow into an inflow,
3. padded interest direction values could fail to apply expense sign handling.

## Actions Taken

Hardened `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`:

1. normalized transaction type before amount and sign logic,
2. normalized interest direction before income/expense sign handling,
3. normalized movement direction before adjustment sign handling,
4. used the normalized transaction type for transfer in/out sign maps.

Added direct unit proof for:

1. padded lower-case `BUY` preserving correct fee-inclusive outflow amount,
2. padded lower-case `INTEREST` and `interest_direction` preserving expense sign,
3. padded lower-case `TRANSFER_OUT` preserving outflow sign.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py -q
33 passed

python -m pytest tests/unit/services/calculators/cashflow_calculator_service -q
56 passed

python -m ruff check src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py
All checks passed
```

Additional note:

```text
python -m ruff check src/services/calculators/cashflow_calculator_service tests/unit/services/calculators/cashflow_calculator_service
```

found existing line-length/import-format debt in neighboring cashflow repository files outside this
slice. The touched calculation files passed Ruff.

## Follow-Up

No API or wiki source change is required because this canonicalizes internal cashflow calculation
inputs. Continue reviewing cashflow rule-cache lookup and repository persistence for the same
normalization and idempotency posture.
