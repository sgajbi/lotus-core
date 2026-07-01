# CR-1246 Outbox Recovery Integrated Proof

Date: 2026-07-01

## Objective

Close the remaining local evidence gap for GitHub issue #670 by proving the failed-outbox recovery
pattern on one real database row: dispatcher-created terminal failure evidence, source-safe
operations diagnostics, governed requeue with audit evidence, and subsequent dispatcher processing.

## Change

- Added a Docker-backed integration test that drives:
  - `OutboxDispatcher` terminal failure persistence.
  - `OperationsService.get_failed_outbox_events(...)` source-safe diagnostic serialization.
  - `OperationsService.requeue_failed_outbox_event(...)` governed requeue and audit creation.
  - `OutboxDispatcher` successful processing of the requeued row.
- Added `outbox_recovery_audit` to the global integration cleanup contract so failed-outbox recovery
  audit rows cannot leak between DB-backed tests.

## Expected Improvement

The failed-outbox recovery path is now protected as a reusable platform pattern instead of a set of
independent unit and route tests. Future changes to dispatcher failure metadata, QCP operations
service mapping, requeue audit semantics, or integration cleanup will fail a focused test before
operators lose incident recovery evidence.

## Tests Added

- `test_failed_outbox_recovery_round_trip_from_dispatcher_to_service_to_dispatcher` covers the
  full failed-outbox recovery lifecycle with a real database row and mocked Kafka delivery
  callbacks.

## Validation Evidence

- Docker-backed integrated recovery proof passed:
  `python -m pytest tests\integration\services\query_service\test_int_operations_service.py::test_failed_outbox_recovery_round_trip_from_dispatcher_to_service_to_dispatcher -q --tb=short`
  -> 1 passed.
- Focused operations service/repository tests passed:
  `python -m pytest tests\unit\services\query_service\services\test_operations_service.py -k "failed_outbox or requeue_failed_outbox_event or outbox_recovery" tests\unit\services\query_service\repositories\test_operations_repository.py -k "failed_outbox or requeue_failed_outbox_event or outbox_recovery" -q --tb=short`
  -> 12 passed, 124 deselected.
- Focused QCP route/OpenAPI evidence passed:
  `python -m pytest tests\integration\services\query_control_plane_service\test_operations_router_dependency.py -k "failed_outbox or requeue_failed_outbox_event or outbox_recovery" tests\integration\services\query_control_plane_service\test_control_plane_app.py -q --tb=short`
  -> 6 passed, 87 deselected.
- Scoped Ruff lint and format checks passed for the edited test files.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed with line-ending warnings only.

## Downstream Compatibility

No API route, request/response schema, Kafka topic, event payload/header, dispatcher happy path, or
business/source-data contract changed. The only runtime-adjacent change is test cleanup of the
already-governed `outbox_recovery_audit` table.

## Documentation And Wiki Decision

This architecture record, codebase review ledger, repository context, and quality/refactor
scorecards were updated because issue #670's local closure evidence changed. No wiki change is
needed for this slice because operator commands and runbook semantics were already documented by
CR-1221 through CR-1224.

## Remaining Follow-Up

- Decide alert thresholds for recovery rejections and unexpected recovery errors after real runtime
  usage is observed.
