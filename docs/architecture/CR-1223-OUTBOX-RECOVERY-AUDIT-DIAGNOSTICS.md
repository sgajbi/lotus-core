# CR-1223 Outbox Recovery Audit Diagnostics

Date: 2026-07-01

## Objective

Continue fixing GitHub issue #670 and the broader operator-diagnostics backlog by making governed
outbox recovery history visible through QCP. The previous slice added `outbox_recovery_audit` and a
controlled requeue command; this slice removes the remaining direct-database dependency for
reviewing recovery attempts.

## Change

- Added `GET /support/outbox/recovery-audits` to the query-control-plane operations surface.
- Added source-safe recovery audit list and record DTOs that expose actor, reason, correlation,
  prior status, new status, outcome, prior retry count, and prior failure metadata.
- Added repository count/page queries over `outbox_recovery_audit` with filters for `outbox_id`,
  `outcome`, `correlation_id`, `requested_by`, and `recovery_action`.
- Added application mapping that returns a stable generated snapshot time and excludes raw outbox
  event payloads.
- Registered the route in the route-family contract registry.

## Expected Improvement

Operators can now review failed-outbox recovery history through the same protected QCP surface used
for failed-row diagnostics and recovery commands. Incident review can answer who requested recovery,
why it was requested, whether it was accepted or rejected, and what prior source-safe failure
evidence existed without direct database reads or raw payload exposure.

## Tests Added

- Service coverage proves recovery audit responses map durable audit rows, preserve prior failure
  summaries, use a stable snapshot time, and do not expose payload fields.
- Repository coverage proves filters, pagination, and ordering over `outbox_recovery_audit`.
- QCP route coverage proves filter wiring and unexpected-error mapping.
- OpenAPI coverage proves the new route, filter documentation, list schema, record schema, and
  payload exclusion are published.

## Validation Evidence

- Focused outbox service, repository, QCP route, and OpenAPI tests passed with 16 tests:
  `python -m pytest tests\unit\services\query_service\services\test_operations_service.py tests\unit\services\query_service\repositories\test_operations_repository.py tests\integration\services\query_control_plane_service\test_operations_router_dependency.py tests\integration\services\query_control_plane_service\test_control_plane_app.py -k "failed_outbox or outbox_recovery or operations_support_parameters"`.
- Scoped Ruff formatting and lint checks passed for touched code and test files.
- `make typecheck` passed with no issues in 50 source files.
- `python -m alembic heads` reported single head `c1008d9e0f1a2`.
- `make lint` passed, including `qcp-problem-details-guard`, `route-contract-family-guard`,
  `source-data-product-contract-guard`, `analytics-input-consumer-contract-guard`,
  `event-runtime-contract-guard`, and `rfc0083-closure-guard`.
- `make route-contract-family-guard`, `make openapi-gate`, `make api-vocabulary-gate`,
  `make quality-openapi-spectral-gate`, and `make quality-wiki-docs-gate` passed.
- `git diff --check` passed with line-ending warnings only on touched documentation files.

## Downstream Compatibility

This is an additive QCP operator read endpoint over an existing audit table. It does not change
Kafka topics, event payloads, outbox dispatcher state transitions, failed-row diagnostics, requeue
request/response shape, business/source-data routes, or front-office contracts.

## Documentation And Wiki Decision

This architecture record, codebase review ledger, route-family registry, operations dashboard
guide, repo-local `wiki/Outbox-Events.md`, repository context, and quality/refactor scorecards were
updated because operator recovery evidence changed platform truth.

## Remaining Follow-Up

- Add Docker-backed integrated proof that dispatcher-created terminal failed rows can be requeued
  through QCP and later processed by the dispatcher.
- Consider failed-row age, recovery outcome, and recovery rejection metrics after the audit table
  has real runtime use.
