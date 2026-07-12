# CR-357 Cost Cash Instrument Detection Normalization

Date: 2026-05-27

## Scope

Reviewed cost-engine strategy resolution for cash instruments after dependency-sorter and
transaction-type normalization.

## Findings

`CostCalculator._resolve_strategy(...)` uses `_is_cash_instrument(...)` to decide whether cash
withdrawals, cash sells, and cash transfer-outs should use cash-outflow semantics instead of strict
security-lot disposal.

That detection path uppercased values without trimming whitespace. Padded source values in
`product_type`, `asset_class`, `instrument_id`, or `security_id` could cause a real cash movement to
be routed through `SecurityOutflowStrategy`. For cash withdrawals with no open security lot, that
can create a false disposal error and leave the calculated cash movement unset.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`:

1. added one shared internal code normalizer using `strip().upper()`,
2. reused it for currency normalization,
3. applied it to cash-instrument detection across product type, asset class, instrument id, and
   security id.

Added direct unit proof that a padded lower-case cash withdrawal:

1. normalizes transaction type and currencies,
2. defaults same-currency FX to `1`,
3. does not call strict security-lot disposal,
4. calculates the cash outflow as `-500` in local and base cost fields.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q
41 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
92 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this improves internal cost-engine route selection
without changing public contracts. Continue reviewing cash-like transaction classification in
upstream ingestion and downstream consumers so source vocabulary is canonicalized early and
calculation execution remains defensive.
