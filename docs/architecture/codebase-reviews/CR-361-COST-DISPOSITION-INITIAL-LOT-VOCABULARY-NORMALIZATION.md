# CR-361 Cost Disposition Initial Lot Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed the cost-engine disposition boundary for historical lot replay after FIFO and average-cost
strategy initial-lot normalization.

## Findings

`DispositionEngine.set_initial_lots(...)` filtered historical BUY rows before delegating to the
cost-basis strategy. The downstream strategies now normalize BUY transaction types, but the
disposition engine pre-filter still accepted only exact `BUY` enum/string values.

That meant padded or lower-case historical BUY rows could still be dropped before reaching the
normalized replay logic, causing replayed SELL, transfer-out, and corporate-action disposal
calculations to see zero or understated available holdings.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/disposition_engine.py`:

1. added a disposition-local BUY classifier using `strip().upper()`,
2. applied it before initial-lot filtering,
3. preserved the existing positive-quantity filter.

Added direct unit proof that padded lower-case historical BUY rows are included for initial lot
seeding while padded lower-case SELL rows are excluded.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_disposition_engine.py -q
5 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
99 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/disposition_engine.py tests/unit/services/calculators/cost_calculator_service/engine/test_disposition_engine.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this improves internal replay behavior without
changing public contracts. Continue reviewing persisted historical transaction loading and
reprocessing paths for remaining pre-calculation filters that can drop canonical transaction roles.
