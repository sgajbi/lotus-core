# CR-1409 Valuation Scheduler Dependency Factory

## Objective

Complete GitHub issue #545 by removing remaining direct DB session/repository construction from
the valuation scheduler loop while keeping the loop itself simple.

## Expected Improvement

`ValuationSchedulerRepositoryFactory` now owns repository construction for scheduler DB steps:

- valuation repository,
- valuation job repository,
- position-state repository, and
- reprocessing-job repository.

`ValuationScheduler` also accepts an explicit session provider. The scheduler remains the cadence
and compatibility wrapper rather than introducing a separate loop framework. This keeps the
design simpler while satisfying the #545 requirement that the loop can be tested without real
repositories or Kafka.

## Compatibility Impact

No poll order, DB transaction boundary, repository query, Kafka dispatch behavior, scheduler
setting, metric, log event name, API contract, database schema, or runtime topology changed.

## Tests Added

Added tests proving:

- scheduler DB-step wrappers use an injected repository factory, and
- one scheduler poll can run with injected session provider, repository factory, and collaborators
  without real repositories or Kafka.

Existing tests continue to cover dispatch, backfill, watermark, reprocessing trigger, stale reset,
queue metrics, shutdown, and environment setting behavior.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m pytest tests\integration\services\valuation_orchestrator_service\test_valuation_scheduler_integration.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler_dependencies.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler_dependencies.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py`
- `python -m mypy src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler_dependencies.py`
- `make lint`
- `git diff --check`

## Issue #545 Closure

This completes the local #545 architecture acceptance criteria:

- scheduler loop is testable without real repositories or Kafka,
- dispatch publisher behavior is isolated in `ValuationJobDispatcher`,
- claimed-job orchestration and recovery are isolated in `ValuationDispatchCoordinator`,
- reprocessing trigger coordination is isolated in `InstrumentReprocessingCoordinator`,
- watermark advancement is isolated in `ValuationWatermarkAdvancer`,
- backfill planning/staging is isolated in `ValuationBackfillPlanner`,
- stale reset policy is isolated in `ValuationStaleJobResetter`, and
- DB session/repository construction is injected through explicit providers/factories.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work keeps orchestration responsibilities in the extracted collaborators and keeps the
scheduler loop small.

No platform skill update is needed for this slice. The reusable lesson is repository-local:
valuation scheduler work should keep loop cadence separate from application orchestration and
infrastructure construction, and that rule is now captured in `REPOSITORY-ENGINEERING-CONTEXT.md`.
