# CR-1186 Outbox Retry Eligibility

Date: 2026-06-30

## Objective

Begin fixing GitHub issue #669 by adding durable retry eligibility for retryable outbox publish
failures, so failed rows are not immediately eligible on every dispatcher poll.

## Change

- Added nullable `outbox_events.next_attempt_at` and an aligned
  `status, next_attempt_at, created_at` claim index.
- Added runtime settings for outbox retry initial delay, max delay, and jitter window.
- Added bounded exponential retry scheduling in `OutboxDispatcher`.
- Changed the dispatcher claim query to process only `PENDING` rows with no `next_attempt_at` or a
  matured `next_attempt_at`.
- Retryable failures now persist `next_attempt_at`; success and terminal failure clear it.

## Expected Improvement

The outbox can distinguish immediately eligible pending rows from pending rows waiting for a
scheduled retry. This reduces retry storms after Kafka degradation and avoids repeatedly locking the
same failed rows before their retry window matures.

## Tests Added

- Runtime settings now cover retry delay and jitter configuration.
- Unit coverage proves bounded exponential retry delay behavior.
- Integration tests were updated to assert persisted `next_attempt_at`, skip immature retry rows,
  and mature a row before retry recovery.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_outbox_dispatcher.py -q` passed with 7
  tests.
- `python -m ruff check ...` passed for the touched outbox, model, migration, and test files.
- `python -m ruff format --check ...` passed for the touched outbox, model, migration, and test
  files.
- `python -m alembic heads` reported single head `c1003d4e5f6a7`.
- `git diff --check` passed.
- Attempted DB-backed focused integration tests:
  `python -m pytest tests/integration/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py -q`
  but local execution was blocked before test bodies by unavailable Docker engine.

## Downstream Compatibility

No Kafka topic, event payload, event header, producer API, success status, terminal failure status,
or existing pending-row compatibility changed. Existing rows with `next_attempt_at IS NULL` remain
immediately eligible, preserving current behavior until a retryable failure schedules them.

The database schema intentionally changes by adding nullable `outbox_events.next_attempt_at` and a
claim-path index.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator-facing command or published runbook changed in this
slice.

## Remaining Follow-Up

- Run the Docker-backed outbox integration tests and migration smoke in GitHub CI or a local Docker
  environment.
- Add pending-waiting metrics and operator diagnostics alongside the broader #670 failed-outbox
  recovery workflow.
- Define any max-elapsed retry budget as part of a shared platform retry profile before enforcing
  it in the dispatcher.
