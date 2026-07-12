# CR-1146 Ingestion Job Retry Workflow Boundary

Date: 2026-06-22

## Scope

Operator-triggered ingestion job retry workflow in
`src/services/event_replay_service/app/routers/ingestion_operations.py`.

## Finding

`retry_ingestion_job(...)` mixed replay-context lookup, missing payload validation, partial retry
payload shaping, retry policy checks, deterministic fingerprint generation, dry-run audit handling,
duplicate replay blocking, payload publication, failed publish bookkeeping, replay bookkeeping,
post-publish bookkeeping failure posture, final job reload, and HTTP error shaping in one C-ranked
route function.

Radon reported:

- `retry_ingestion_job`: `C (11)`

## Action Taken

Extracted focused helpers for:

- required replay-context lookup,
- retry payload shaping and HTTP error posture,
- retry policy enforcement,
- retry audit recording,
- dry-run retry handling,
- duplicate deterministic replay blocking,
- replay publication and failed-publish bookkeeping,
- successful replay bookkeeping and post-publish failure posture,
- final job reload.

The route path, request/response contract, deterministic replay fingerprint inputs, audit statuses,
publish sequence, duplicate-block error body, pause-mode error body, and bookkeeping failure body
remain unchanged.

## Evidence

Focused unit proof:

- `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations.py -q`
- Result: `7 passed`

Focused route proof:

- `python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_partial_retry_dry_run tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_full_retry_returns_complete_job_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_retry_blocks_unsupported_partial_scope_and_paused_mode -q`
- Result: `3 passed`

Focused static proof:

- `python -m ruff check src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/event_replay_service/test_ingestion_operations.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/event_replay_service/test_ingestion_operations.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/event_replay_service/app/routers/ingestion_operations.py -s --exclude "*/build/*"`
- Result: `retry_ingestion_job` is `A (2)`

Measured movement:

- `retry_ingestion_job`: `C (11)` -> `A (2)`

## Residual Risk

This slice does not change ingestion retry policy, deterministic fingerprint methodology, Kafka
publication implementation, replay audit persistence schema, or job state transitions. The larger
`replay_consumer_dlq_event(...)` route function remains a separate measured hotspot.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of operator-triggered retry control flow,
- separation of publish and bookkeeping failure postures,
- audit status consistency for dry-run, duplicate-blocked, failed, replayed, and bookkeeping-failed
  outcomes.

It does not claim full bank-buyable readiness for `lotus-core`.
