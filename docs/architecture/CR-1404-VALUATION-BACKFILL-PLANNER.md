# CR-1404 Valuation Backfill Planner

## Objective

Continue GitHub issue #545 by moving valuation backfill planning and staging out of
`ValuationScheduler` into a dedicated collaborator.

## Expected Improvement

`ValuationBackfillPlanner` now owns:

- latest-business-date backfill input flow,
- no-history state partitioning,
- non-reprocessing no-history normalization,
- reprocessing no-history deferral logging,
- backfill gap metrics,
- deterministic scheduler backfill correlation IDs,
- valuation job request construction,
- bounded backfill chunking, and
- backfill job upsert/staging metrics.

`ValuationScheduler` now wires repositories for the current DB transaction and delegates the
backfill use case to the planner. This reduces scheduler responsibility while preserving the
existing deployment shape and DB transaction ownership.

## Compatibility Impact

No scheduler setting, database query, job upsert contract, correlation ID format, metric name,
status vocabulary, Kafka behavior, API contract, database schema, or runtime topology changed.
`ValuationScheduler._create_backfill_jobs(...)` remains as a compatibility wrapper for existing
internal callers and DB-backed integration tests.

## Tests Added

Added a direct planner unit test proving backfill jobs are planned and staged without exercising
the scheduler loop.

Existing scheduler and DB-backed tests continue to cover:

- position-aware backfill start dates,
- backfill rearming after watermark reset,
- bounded chunks across states,
- no-history normalization,
- reprocessing no-history deferral,
- zombie backlog draining, and
- missing-instrument backfill skip behavior.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_backfill_planner.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_backfill_planner.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py`
- `python -m mypy src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_backfill_planner.py`

## Remaining #545 Scope

This does not close #545. Remaining fixed-local acceptance requires extracting and testing:

- scheduler loop/poll cadence,
- instrument reprocessing trigger coordination,
- watermark advancement,
- stale valuation job reset, and
- DB session/repository factory ownership.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work keeps backfill planning out of the scheduler.
