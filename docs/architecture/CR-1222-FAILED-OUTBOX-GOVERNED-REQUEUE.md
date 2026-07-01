# CR-1222 Failed Outbox Governed Requeue

Date: 2026-07-01

## Objective

Continue fixing GitHub issue #670 by adding controlled recovery for terminal failed outbox rows.
The previous slice exposed source-safe diagnostics; this slice adds a governed requeue command with
durable audit evidence and rejects blind retries.

## Change

- Added `outbox_recovery_audit` with actor, reason, correlation, prior status, new status,
  outcome, prior retry count, and prior failure metadata.
- Added `POST /support/outbox/failed-events/{outbox_id}/requeue` on the QCP operations surface.
- Added request and response DTOs requiring operator identity, source-safe reason, optional
  correlation, and explicit payload-contract review confirmation.
- Added repository logic that locks the outbox row, rejects non-`FAILED` rows, rejects requests
  without payload-contract review confirmation, records rejected recovery attempts when a row is
  found, and atomically moves valid rows back to `PENDING`.
- Controlled requeue resets dispatcher retry state and immediate eligibility while preserving prior
  source-safe failure evidence in the recovery audit row.

## Expected Improvement

Operators now have a source-safe, auditable path from failed-row diagnostics to recovery. The
platform no longer requires a direct database update to retry a terminal failed outbox row, and it
does not allow an operator or automation workflow to requeue a poison event without an explicit
contract-review acknowledgement.

## Tests Added

- Service coverage proves requeue responses carry audit IDs, status transition, retry reset, and
  source-safe redacted reasons.
- Repository coverage proves successful requeue records audit evidence, resets dispatcher state,
  clears stale failure metadata from the pending row, and preserves prior failure evidence in audit.
- Repository coverage proves blind requeue is rejected, audited, and leaves the row terminal
  `FAILED`.
- QCP route coverage proves successful request wiring and rejected recovery mapping to stable
  `409 QCP_OUTBOX_RECOVERY_REJECTED`.
- OpenAPI coverage proves the requeue command, confirmation field, audit response fields, and 409
  problem example are published.

## Validation Evidence

- Focused failed-outbox diagnostics/requeue service, repository, QCP route, and OpenAPI tests
  passed with 10 tests.
- Scoped Ruff check passed for touched model, migration, DTO, repository, service, router, and test
  files.
- Scoped Ruff format check passed for touched model, migration, DTO, repository, service, router,
  and test files.
- `python -m alembic heads` reported single head `c1008d9e0f1a2`.
- `make typecheck` passed with no issues in 50 source files.
- `make lint` passed, including `qcp-problem-details-guard`, `route-contract-family-guard`,
  `source-data-product-contract-guard`, `analytics-input-consumer-contract-guard`,
  `event-runtime-contract-guard`, and `rfc0083-closure-guard`.
- `make route-contract-family-guard` passed after registering
  `POST /support/outbox/failed-events/{outbox_id}/requeue`.
- `make openapi-gate`, `make api-vocabulary-gate`, and `make quality-openapi-spectral-gate`
  passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.

## Downstream Compatibility

This is an additive QCP operator command and additive database table. It does not change Kafka
topic names, event payloads, event headers, dispatcher success semantics, business/source-data
routes, front-office contracts, or existing failed-row diagnostics. Failed rows are requeued only
when the new operator command is called successfully.

## Documentation And Wiki Decision

This architecture record, codebase review ledger, route-family registry, operations dashboard
guide, repo-local `wiki/Outbox-Events.md`, repository context, and quality/refactor scorecards were
updated because an operator recovery command changed platform truth.

## Remaining Follow-Up

- Add Docker-backed integrated proof that dispatcher-created terminal failed rows can be requeued
  through QCP and later processed by the dispatcher.
- Consider listing recent `outbox_recovery_audit` rows if operators need post-recovery history in
  QCP beyond direct database inspection.
- Consider failed-row age and recovery outcome metrics after the audit table has real runtime use.
