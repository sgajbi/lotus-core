# CR-1406 Instrument Reprocessing Coordinator

## Objective

Continue GitHub issue #545 by moving instrument-level valuation reprocessing trigger coordination
out of `ValuationScheduler`.

## Expected Improvement

`InstrumentReprocessingCoordinator` now owns:

- pending instrument reprocessing trigger metric updates,
- bounded trigger claiming,
- durable `RESET_WATERMARKS` replay-job creation,
- source trigger correlation propagation, and
- trigger-claim/consume structured logging.

`ValuationScheduler` now wires repositories for the current DB transaction and delegates
instrument reprocessing work to the coordinator.

## Compatibility Impact

No trigger claim query, replay-job type, replay-job payload shape, correlation ID propagation,
metric name, log event name, scheduler setting, API contract, database schema, Kafka behavior, or
runtime topology changed. `ValuationScheduler._process_instrument_level_triggers(...)` and
`_update_reprocessing_metrics(...)` remain as compatibility wrappers for existing internal callers
and tests.

## Tests Added

Added a direct coordinator unit test proving durable replay-job creation can run without exercising
the scheduler loop.

Existing scheduler tests continue to cover:

- pending trigger metric updates,
- trigger claim batch sizing,
- replay-job payload shape, and
- scheduler poll orchestration order.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\instrument_reprocessing_coordinator.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\instrument_reprocessing_coordinator.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py`
- `python -m mypy src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\instrument_reprocessing_coordinator.py`

## Remaining #545 Scope

This does not close #545. Remaining fixed-local acceptance requires extracting and testing:

- scheduler loop/poll cadence,
- stale valuation job reset,
- claimed-job dispatch orchestration/recovery ownership, and
- DB session/repository factory ownership.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work keeps trigger coordination out of the scheduler.
