# CR-1187 Outbox Failure Metadata

Date: 2026-06-30

## Objective

Begin fixing GitHub issue #670 by persisting source-safe structured failure metadata on outbox rows
when Kafka delivery fails, especially when a row reaches terminal `FAILED` status.

## Change

- Added nullable outbox failure metadata fields:
  `last_failure_reason_code`, `last_failure_category`, `last_failure_message`, and
  `last_failure_at`.
- Added a `status, last_failure_at` index for failed-row support diagnostics.
- Added shared redaction-based failure-message sanitization and length bounding in the outbox
  dispatcher.
- Retryable and terminal delivery failures now persist structured last-failure metadata.
- Successful delivery clears stale failure metadata.

## Expected Improvement

Operators and later recovery workflows can diagnose failed outbox rows from durable row-level
evidence instead of relying only on logs and aggregate metrics. Failure messages are source-safe:
credential-like values are redacted and messages are bounded before persistence.

## Tests Added

- Unit coverage proves failure metadata uses safe reason codes/categories, redacts sensitive text,
  and bounds persisted messages.
- Unit coverage proves terminal failure updates include structured failure metadata.
- Existing Docker-backed terminal failure integration assertions were extended to check persisted
  failure metadata when that lane runs in CI.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_outbox_dispatcher.py -q` passed with 9
  tests.
- `python -m alembic heads` reported single head `c1004e5f6a7b8`.
- `python -m ruff check ...` passed for the touched outbox, model, migration, and test files.
- `python -m ruff format --check ...` passed for the touched outbox, model, migration, and test
  files.
- `git diff --check` passed.
- Docker-backed outbox integration execution remains locally blocked by unavailable Docker engine;
  CR-1186 records the failed local attempt and this slice requires CI/Docker proof before issue
  closure.

## Downstream Compatibility

No Kafka topic, event payload, event header, producer API, success status, terminal failure status,
or happy-path publishing behavior changed. The database schema intentionally changes by adding
nullable failure metadata columns and a support-diagnostics index.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required yet because this slice does not add an operator command, requeue API, or
published recovery runbook.

## Remaining Follow-Up

- Add a protected operator view for failed outbox rows without raw payloads.
- Add governed requeue/recovery controls with actor, reason, correlation ID, prior/new status, and
  outcome evidence.
- Add pending-waiting and failed-row diagnostics metrics alongside the retry-eligibility work from
  CR-1186.
- Prove the DB-backed outbox integration tests in GitHub CI or a Docker-enabled local run.
