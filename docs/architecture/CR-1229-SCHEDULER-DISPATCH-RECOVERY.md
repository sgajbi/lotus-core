# CR-1229 Scheduler Dispatch Recovery

Date: 2026-07-01

## Objective

Fix GitHub issue #596 by recovering valuation and aggregation jobs immediately when scheduler
dispatch fails after the jobs have already been claimed into `PROCESSING`. The slice promotes the
platform pattern that claim-and-publish control queues must not rely only on stale-job reset for
known dispatch failures.

## Change

- Added shared scheduler dispatch recovery vocabulary in
  `portfolio_common.scheduler_dispatch_recovery`.
- Added repository-level `recover_dispatch_failed_jobs(...)` methods for valuation and aggregation
  jobs.
- Recovery updates only rows still in `PROCESSING` and applies attempt-budget policy:
  retryable rows return to `PENDING`, rows at or above the configured max attempts move to
  `FAILED`.
- Valuation and aggregation schedulers now classify synchronous publish failures with:
  affected recovery job IDs, remaining unpublished record keys, already-published record keys, and
  failure phase.
- Delivery-confirmation timeouts now carry an explicit `delivery_confirmation_timeout` phase and
  recover the affected claimed rows immediately instead of waiting for stale timeout.

## Expected Improvement

Kafka publish failures and delivery-confirmation timeouts no longer strand claimed valuation or
aggregation jobs in `PROCESSING` until the next stale-job timeout. Operators can see a durable
failure reason on the affected job rows, and retry eligibility follows the same configured attempt
budget as stale-job recovery.

## Tests Added

- Valuation scheduler coverage for publish failure before the first job, mid-batch publish failure,
  mid-batch publish failure with queued-work flush timeout, flush timeout classification, and
  immediate recovery before the next poll.
- Aggregation scheduler coverage for publish failure before the first job, mid-batch publish
  failure, mid-batch publish failure with queued-work flush timeout, flush timeout classification,
  and immediate recovery before the next poll.
- Valuation repository coverage proving dispatch recovery fences on `PROCESSING` rows and uses
  `attempt_count >= max_attempts` for terminal failure versus retryable pending recovery.
- Aggregation repository coverage proving the same durable recovery contract.

## Validation Evidence

- Focused valuation tests passed:
  `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py tests\unit\services\calculators\position_valuation_calculator\repositories\test_valuation_repository_worker_metrics.py -q`
  with 43 tests.
- Focused aggregation tests passed:
  `python -m pytest tests\unit\services\portfolio_aggregation_service\core\test_aggregation_scheduler.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py -q`
  with 21 tests.
- Combined focused selection passed:
  `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py tests\unit\services\calculators\position_valuation_calculator\repositories\test_valuation_repository_worker_metrics.py tests\unit\services\portfolio_aggregation_service\core\test_aggregation_scheduler.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py -q`
  with 64 tests.
- Scoped Ruff lint passed for touched source and test files.
- Scoped Ruff format check passed for touched source and test files.
- Type checking passed:
  `make typecheck`.
- Repository lint gate passed:
  `make lint`.
- Wiki/documentation gate passed:
  `make quality-wiki-docs-gate`.
- Whitespace diff check passed:
  `git diff --check`.

## Downstream Compatibility

No API route, OpenAPI contract, database schema, Kafka topic, event payload, success DTO, or
consumer contract changed. The intentional behavior change is internal scheduler recovery for rows
already claimed into `PROCESSING` after dispatch failure.

Existing stale-job reset remains as a safety net for crashes and unknown failures. This slice adds
immediate recovery for failures the scheduler already observes directly.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, repository context, quality scorecard,
and refactor health report. No repo-local wiki update is required because no public API, operator
command, or runbook workflow changed.

## Remaining Follow-Up

- Keep issue #596 open for PR/CI/QA evidence and Docker-backed proof against the real Kafka-backed
  scheduler runtime.
- Consider adding bounded metrics for dispatch recovery outcomes if runtime usage shows operators
  need fleet-level visibility beyond existing control queue pending/failed gauges and durable
  failure reasons.
