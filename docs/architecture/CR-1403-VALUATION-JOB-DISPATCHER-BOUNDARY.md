# CR-1403 Valuation Job Dispatcher Boundary

## Objective

Start GitHub issue #545 by removing valuation job publish/flush/recovery message construction
from `ValuationScheduler` and placing it behind a dedicated dispatch service.

## Expected Improvement

`ValuationJobDispatcher` now owns:

- valuation job record-key construction,
- `PortfolioValuationRequiredEvent` payload mapping,
- correlation headers,
- dispatch budget enforcement,
- publisher delivery confirmation, and
- `SchedulerDispatchError` recovery metadata for publish and flush failures.

The scheduler still owns polling cadence, job claiming, DB transactions, and dispatch recovery
state changes. This keeps the first slice small while making the Kafka/outbox dispatch boundary
independently testable before the remaining #545 extraction of backfill, watermark, and
reprocessing collaborators.

## Compatibility Impact

No Kafka topic, payload, key, header, dispatch recovery behavior, database schema, scheduler
settings, metric name, or runtime topology changed. `ValuationScheduler._dispatch_jobs(...)`
remains as a compatibility wrapper around the dispatcher for existing internal callers and tests.

## Tests Added

Added a direct dispatcher unit test proving claimed valuation jobs can be published without
instantiating or exercising the scheduler loop.

Existing scheduler dispatch tests continue to cover:

- correlation header omission,
- partial publish failures,
- flush timeout recovery,
- budget exhaustion,
- claimed-batch loop stop conditions, and
- dispatch recovery.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_job_dispatcher.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_job_dispatcher.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py`

## Remaining #545 Scope

This does not close #545. Remaining fixed-local acceptance requires extracting and testing:

- scheduler loop/poll cadence,
- instrument reprocessing trigger coordination,
- watermark advancement,
- backfill planning/staging,
- stale valuation job reset, and
- DB session/repository factory ownership.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work follows the new dispatcher boundary instead of reintroducing publisher logic in the
scheduler.
