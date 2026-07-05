# CR-1407 Valuation Stale Job Resetter

## Objective

Continue GitHub issue #545 by moving stale valuation job reset policy out of
`ValuationScheduler`.

## Expected Improvement

`ValuationStaleJobResetter` now owns stale-job reset invocation with scheduler-configured timeout
and maximum-attempt policy. `ValuationScheduler` wires the repository for the current DB transaction
and delegates the job-state reset policy to the resetter.

## Compatibility Impact

No stale-job repository method, timeout setting, max-attempt setting, job status behavior, metric,
API contract, database schema, Kafka behavior, or runtime topology changed.
`ValuationScheduler._reset_stale_valuation_jobs(...)` remains as a compatibility wrapper for
existing poll orchestration and tests.

## Tests Added

Added a direct resetter unit test proving stale reset policy forwards the configured timeout and
max-attempt values without exercising the scheduler loop.

Existing scheduler tests continue to cover poll orchestration and environment-driven timeout and
attempt settings.

## Validation Evidence

Local focused validation:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
- `python -m ruff check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_stale_job_resetter.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py --ignore E501,I001`
- `python -m ruff format --check src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_stale_job_resetter.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py`
- `python -m mypy src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py src\services\valuation_orchestrator_service\app\core\valuation_stale_job_resetter.py`

## Remaining #545 Scope

This does not close #545. Remaining fixed-local acceptance requires extracting and testing:

- scheduler loop/poll cadence,
- claimed-job dispatch orchestration/recovery ownership, and
- DB session/repository factory ownership.

## Documentation Decision

No wiki update is needed for this slice because no operator runbook, endpoint, deployment command,
or runtime configuration contract changed. Repository engineering context was updated so future
scheduler work keeps stale-reset policy out of the scheduler.
