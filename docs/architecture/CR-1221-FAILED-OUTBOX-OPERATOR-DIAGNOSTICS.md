# CR-1221 Failed Outbox Operator Diagnostics

Date: 2026-07-01

## Objective

Continue fixing GitHub issue #670 by exposing protected, source-safe failed-outbox evidence through
the query control plane so operators can inspect terminal publish failures without querying raw
database rows or viewing raw event payloads.

## Change

- Added `GET /support/outbox/failed-events` to the query control plane operations surface.
- Added `FailedOutboxEventRecord` and `FailedOutboxEventListResponse` DTOs for failed outbox row
  diagnostics.
- Added operations repository and service methods that list only terminal `FAILED` outbox rows with
  pagination and optional aggregate, event-type, topic, correlation, and reason-code filters.
- Excluded raw outbox `payload` from the response and marked returned rows as `retry_safe=false`
  until a separate governed requeue workflow validates poison-event risk.
- Added OpenAPI and route-level tests pinning the source-safe response contract and filter wiring.

## Expected Improvement

Operators can now move from an aggregate failed-outbox alert to bounded row-level evidence through a
governed QCP endpoint. This improves incident triage while preserving the security boundary: raw
payloads, client data, secrets, and stack traces are not exposed by the diagnostic API.

## Tests Added

- Service unit coverage proves failed rows are mapped into source-safe operator records and raw
  payloads are not present on the DTO.
- QCP route coverage proves every filter is forwarded to the service and unexpected failures remain
  mapped through the standard operations error handler.
- OpenAPI coverage proves the failed-outbox route, reason-code filter, payload-exclusion language,
  and DTO field descriptions are documented.

## Validation Evidence

- Focused failed-outbox service, repository, QCP route, and OpenAPI tests passed with 6 tests.
- Scoped Ruff check passed for the touched service, repository, DTO, router, and test files.
- Scoped Ruff format check passed for the touched service, repository, DTO, router, and test files.
- `make typecheck` passed with no issues in 50 source files.
- `make lint` passed, including `qcp-problem-details-guard`, `route-contract-family-guard`,
  `source-data-product-contract-guard`, `analytics-input-consumer-contract-guard`,
  `event-runtime-contract-guard`, and `rfc0083-closure-guard`.
- `make route-contract-family-guard` passed after registering
  `GET /support/outbox/failed-events`.
- `make openapi-gate`, `make api-vocabulary-gate`, and `make quality-openapi-spectral-gate`
  passed.
- `make quality-wiki-docs-gate` passed after updating repo-local wiki source.
- `git diff --check` passed.

## Downstream Compatibility

This is an additive QCP operator-support endpoint. No business API route, source-data product,
Kafka topic, event payload, event header, database write behavior, dispatcher retry behavior, or
front-office contract changes.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, operations dashboard guide, repo-local
`wiki/Outbox-Events.md`, repository context, and quality/refactor scorecards were updated because an
operator-facing diagnostic surface changed.

## Remaining Follow-Up

- CR-1222 adds governed requeue/recovery controls with actor, reason, correlation ID, prior/new
  status, and outcome evidence.
- Add Docker-backed proof that terminal failed rows created by the dispatcher are visible through the
  QCP route in the integrated runtime.
- Consider failed-row age and reason-code metrics once the first operator view has stabilized.
