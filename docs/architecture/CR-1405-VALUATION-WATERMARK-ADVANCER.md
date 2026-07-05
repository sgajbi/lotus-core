# CR-1405 Valuation Watermark Advancer

## Objective

Continue GitHub issue #545 by moving valuation watermark advancement and terminal reprocessing
normalization out of `ValuationScheduler`.

## Expected Improvement

`ValuationWatermarkAdvancer` now owns:

- latest-business-date watermark input loading,
- lagging and terminal reprocessing state retrieval,
- first-open-date support lookups,
- active reprocessing gauge updates,
- terminal reprocessing normalization,
- contiguous snapshot date lookup,
- epoch-fenced watermark update construction,
- stale-skip warning/metric handling, and
- current-vs-reprocessing status preservation.

`ValuationScheduler` now wires repositories for the current DB transaction and delegates watermark
advancement to the advancer.

## Compatibility Impact

No database query contract, watermark status vocabulary, epoch-fence behavior, metric name, log
event name, scheduler setting, API contract, database schema, Kafka behavior, or runtime topology
changed. `ValuationScheduler._advance_watermarks(...)` remains as a compatibility wrapper for
existing internal callers and DB-backed integration tests.

## Tests Added

Added a direct advancer unit test proving watermark advancement can run without exercising the
scheduler loop.

Existing scheduler and DB-backed tests continue to cover:

- terminal reprocessing normalization,
- partial epoch-fenced updates,
- first-open-date support for sentinel watermarks,
- active lagging state advancement, and
- DB-backed watermark advancement against persisted snapshots.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m pytest tests\integration\services\valuation_orchestrator_service\test_valuation_scheduler_integration.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_watermark_advancer.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py tests\integration\services\valuation_orchestrator_service\test_valuation_scheduler_integration.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_watermark_advancer.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py tests\integration\services\valuation_orchestrator_service\test_valuation_scheduler_integration.py`
- `python -m mypy src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_watermark_advancer.py`

## Remaining #545 Scope

This does not close #545. Remaining fixed-local acceptance requires extracting and testing:

- scheduler loop/poll cadence,
- instrument reprocessing trigger coordination,
- stale valuation job reset, and
- DB session/repository factory ownership.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work keeps watermark policy out of the scheduler.
