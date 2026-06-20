# CR-1119: Cost Engine Event-Building Boundary

Date: 2026-06-20

## Scope

`CostCalculatorConsumer._build_cost_engine_events_to_publish(...)` was the remaining B-ranked method
in the cost calculator consumer. It mixed history loading, engine input transformation, optional
instrument metadata enrichment, FX enrichment, transaction processor orchestration, engine-error
handling, processed-new persistence, and BUY/SELL open-lot quantity updates.

## Change

- Extracted cost-engine transaction input loading and enrichment into
  `_load_cost_engine_transactions(...)`.
- Extracted persistence of processed new transactions into
  `_persist_new_processed_transactions(...)`.
- Extracted BUY/SELL-only open-lot quantity updates into
  `_update_open_lot_quantities_if_required(...)`.
- Added direct regression coverage proving non-BUY/SELL events do not update lot quantities while
  SELL events still do.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer tests/unit/services/calculators/cost_calculator_service/engine -q`
- `python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- `python -m ruff format --check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- `make lint`
- `make typecheck`
- `make quality-maintainability-gate`
- `make quality-complexity-gate`
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- `git diff --check`
- Radon no longer reports any B-ranked method in `cost_calculator_service/app/consumer.py`;
  `consumer.py` remains A-ranked maintainability at `A (19.49)`.

## Follow-Up

Continue reducing cost-calculator engine strategy hotspots with direct domain proof for cost basis,
realized P&L, FX, fee, and open-lot state behavior.
