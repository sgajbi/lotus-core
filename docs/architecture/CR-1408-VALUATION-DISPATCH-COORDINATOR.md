# CR-1408 Valuation Dispatch Coordinator

## Objective

Continue GitHub issue #545 by moving claimed-job dispatch orchestration and recovery out of
`ValuationScheduler`.

## Expected Improvement

`ValuationDispatchCoordinator` now owns:

- bounded claim rounds per poll,
- poll-budget enforcement,
- eligible valuation job claiming,
- claimed-job metrics,
- dispatch callback orchestration,
- dispatch failure stop observation,
- dispatch recovery repository calls, and
- failure-reason construction for recovered jobs.

The scheduler retains the compatibility wrapper `_claim_and_dispatch_ready_jobs(...)`, but the
claim/recover loop is now independently testable and receives its DB session provider and
repository factory explicitly.

## Compatibility Impact

No eligible-job claim query, dispatch payload, dispatch recovery failure reason, max-attempt
setting, poll-budget setting, metric name, log event name, API contract, database schema, Kafka
behavior, or runtime topology changed.

## Tests Added

Added a direct dispatch coordinator unit test proving claimed jobs can be claimed and dispatched
without exercising the scheduler loop.

Existing scheduler tests continue to cover:

- partial-batch stop behavior,
- dispatch failure recovery before the next poll,
- poll-budget exhaustion,
- dispatch-budget recovery,
- producer backpressure metric observation, and
- compatibility wrapper behavior.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_dispatch_coordinator.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_dispatch_coordinator.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py`
- `python -m mypy src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_dispatch_coordinator.py`

## Remaining #545 Scope

This does not close #545. Remaining fixed-local acceptance requires extracting and testing:

- scheduler loop/poll cadence,
- DB poll-step session ownership, and
- repository factory ownership for scheduler DB-step wrappers.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work keeps claimed-job dispatch orchestration and recovery out of the scheduler.
