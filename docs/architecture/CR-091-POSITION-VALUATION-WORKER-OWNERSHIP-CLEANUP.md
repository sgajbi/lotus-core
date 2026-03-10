# CR-091 Position Valuation Worker Ownership Cleanup

## Scope

- `src/services/calculators/position_valuation_calculator/app/*`
- `tests/unit/services/calculators/position_valuation_calculator/*`
- `docs/Database-Schema-Catalog.md`

## Finding

After the valuation split, `position_valuation_calculator` had become a pure worker runtime:

- consume valuation jobs
- compute valuation
- publish completion via outbox

But the package still carried a second, unused orchestration surface:

- `app/core/valuation_scheduler.py`
- `app/core/reprocessing_worker.py`
- `app/consumers/price_event_consumer.py`
- `app/consumers/valuation_readiness_consumer.py`
- `app/settings.py`

None of those files were wired into the service runtime anymore. Only stale unit tests and a few
current-state docs were keeping them alive.

## Change

- Deleted the dead orchestration/runtime residue from `position_valuation_calculator`
- Deleted the orphaned unit tests that only exercised the removed dead paths
- Corrected current-state schema catalog references to the live ownership surface in
  `valuation_orchestrator_service`
- Fixed stale copied path headers in the surviving orchestrator files
- Restored the still-valid scheduler, reprocessing worker, and consumer behavior tests under
  `tests/unit/services/valuation_orchestrator_service/` so ownership cleanup did not reduce
  coverage on the live runtime

## Result

`position_valuation_calculator` now reflects its real ownership boundary:

- live valuation worker only
- no shadow scheduler or reprocessing worker
- no fake worker-local settings for non-existent runtime responsibilities

This removes a second non-running orchestrator implementation from the codebase and reduces the
risk of future fixes being applied to the wrong service.

## Evidence

- runtime wiring:
  - `src/services/calculators/position_valuation_calculator/app/consumer_manager.py`
  - `src/services/valuation_orchestrator_service/app/consumer_manager.py`
- focused validation:
  - `python -m pytest tests/unit/services/calculators/position_valuation_calculator/core/test_consumer_manager_runtime.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py -q`
  - `python -m pytest tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py tests/unit/services/valuation_orchestrator_service/consumers/test_valuation_readiness_consumer.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py -q`
