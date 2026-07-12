# CR-1230 Analytics Export Execution Timeout

Date: 2026-07-01

## Objective

Fix GitHub issue #597 by bounding analytics export execution in `query_service` and making
request cancellation recover the durable export job state. The slice promotes the reusable pattern
that inline application-service jobs must have an explicit execution budget and a source-safe
terminal state when the service observes timeout or cancellation.

## Change

- Added `LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS`, parsed through the shared
  query-service runtime settings helper with strict non-local validation.
- Wrapped analytics export dataset collection and result materialization in an overall
  `asyncio.wait_for(...)` execution budget.
- Extracted `_execute_export_job(...)` so collection and completion stay one bounded application
  operation rather than duplicated inline steps.
- Timeout now marks the durable job `failed` with
  `Analytics export execution exceeded configured timeout.` and returns the existing export job
  response shape.
- Request cancellation now shields the durable failure update, marks the job `failed` with
  `Analytics export execution was cancelled before completion.`, increments failed-job metrics,
  and re-raises cancellation so the ASGI/request runtime can stop the request correctly.

## Expected Improvement

Slow or unexpectedly large analytics exports no longer run without an explicit request-path budget.
Operators and support APIs can inspect a durable failed job with bounded reason text instead of
having a request worker block indefinitely or leave an ambiguous running row after cancellation.

The current lifecycle mode remains `inline_job_execution`; this slice intentionally does not add a
new background worker or queue. A separately owned async runner can later change the lifecycle mode
and return long-lived `accepted` or `running` jobs while using this timeout/cancellation policy as
the terminal-state pattern.

## Tests Added

- Analytics export service test proving timeout marks the job failed, preserves the existing
  response contract, and does not complete a cancelled result.
- Analytics export service test proving `asyncio.CancelledError` marks the job failed with the
  cancellation reason and then re-raises.
- Settings tests proving the execution timeout default, override, and strict invalid-value
  behavior.
- Existing export tests continue to prove successful completion, completed-job reuse,
  fresh-running-job reuse, stale-running-job replacement, input-error failure, and unexpected-error
  failure visibility.

## Validation Evidence

- Focused export/settings suite passed:
  `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_execution.py tests/unit/services/query_service/services/test_analytics_export_results.py tests/unit/services/query_service/test_query_service_settings.py -q`
  with 90 tests.
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

No route path, OpenAPI schema, response DTO, database schema, result payload shape, result
endpoint, or source-data product contract changed. The additive configuration variable has a
default of 300 seconds.

The intentional behavior change is that export execution exceeding the configured budget, or a
request cancellation observed during export execution, now transitions the durable job to `failed`
with bounded reason text.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, repository context, quality scorecard,
and refactor health report. No repo-local wiki update is required because no operator command,
route navigation, public API field, or wiki workflow changed.

## Remaining Follow-Up

- Keep issue #597 open for PR/CI/QA evidence and Docker-backed proof against the real query-service
  runtime.
- Consider a later async export runner with a separate session/worker boundary if export use grows
  beyond inline request-path execution.
- Consider adding bounded timeout/cancellation outcome metrics if operators need a fleet-level
  split beyond the existing completed/failed job counter.
