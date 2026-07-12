# CR-1224 Outbox Recovery Outcome Metrics

Date: 2026-07-01

## Objective

Continue fixing GitHub issue #670 by making governed failed-outbox recovery attempts observable in
Prometheus. The previous slices added diagnostics, recovery commands, and recovery audit listing;
this slice adds a bounded metric pattern so operators can detect accepted, rejected, not-found, and
unexpected-error recovery outcomes without inspecting logs or raw audit rows first.

## Change

- Added `outbox_recovery_attempts_total` in `portfolio_common.monitoring`.
- Instrumented `OperationsService.requeue_failed_outbox_event(...)` to observe:
  - `REQUEUED / outbox_row_requeued_for_dispatch`
  - `REJECTED / <stable rejection reason>`
  - `NOT_FOUND / outbox_row_not_found`
  - `ERROR / unexpected_error`
- Kept metric labels bounded to `recovery_action`, `outcome`, and stable `reason`.
- Extended the shared monitoring label guard to reject sensitive or high-cardinality labels such as
  `outbox_id`, `correlation_id`, `requested_by`, client/account/portfolio/security IDs, traces, and
  request/response bodies.

## Expected Improvement

Recovery controls are now observable at fleet level. Operators can alert or dashboard on rejected
or failing recovery attempts without exposing actor names, incident IDs, raw payloads, or business
identifiers as Prometheus labels.

## Tests Added

- Service tests prove successful, rejected, not-found, and unexpected failed-outbox recovery
  attempts increment the bounded metric with stable labels while preserving existing exception
  behavior.
- Monitoring tests prove production Prometheus metrics do not use sensitive/high-cardinality label
  names and that the outbox recovery counter uses only the approved bounded labels.

## Validation Evidence

- Focused service metric tests passed with 4 selected tests:
  `python -m pytest tests\unit\services\query_service\services\test_operations_service.py -k "requeue_failed_outbox_event" -q`.
- Monitoring label tests passed with 2 tests:
  `python -m pytest tests\unit\libs\portfolio-common\test_monitoring.py -q`.
- Scoped Ruff formatting and lint checks passed for touched monitoring, service, and test files.
- `make typecheck` passed with no issues in 50 source files.
- `make lint` passed, including QCP problem-details, route-family, source-data-product,
  analytics-input-consumer, event-runtime, and RFC-0083 closure guards.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed with line-ending warnings only on touched documentation files.

## Downstream Compatibility

This is additive Prometheus instrumentation only. It does not change QCP route paths, request/response
schemas, HTTP status mapping, database schema, Kafka topics, event payloads, event headers,
dispatcher semantics, or failed-row recovery behavior.

## Documentation And Wiki Decision

This architecture record, codebase review ledger, operations dashboard guide, repo-local
`wiki/Outbox-Events.md`, repository context, and quality/refactor scorecards were updated because
operator observability truth changed.

## Remaining Follow-Up

- Add Docker-backed integrated proof that dispatcher-created terminal failed rows can be requeued
  through QCP and later processed by the dispatcher.
- Decide alert thresholds for recovery rejections and unexpected recovery errors after real runtime
  usage is observed.
