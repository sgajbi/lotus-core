# CR-1147 Consumer DLQ Replay Workflow Boundary

Date: 2026-06-22

## Scope

Correlated consumer dead-letter replay workflow in
`src/services/event_replay_service/app/routers/ingestion_operations.py`.

## Finding

`replay_consumer_dlq_event(...)` mixed missing DLQ-event handling, no-correlation posture,
correlated ingestion-job lookup, durable replay-context lookup, deterministic fingerprint
generation, not-replayable audit responses, duplicate replay blocking, retry-policy enforcement,
dry-run audit response, replay publication, failed-publish response, replay bookkeeping,
post-publish bookkeeping failure posture, and final response assembly in one C-ranked route
function.

Radon reported:

- `replay_consumer_dlq_event`: `C (18)`

## Action Taken

Extracted focused helpers for:

- required DLQ-event lookup,
- correlated ingestion-job resolution,
- replay candidate/context resolution,
- not-replayable audit response recording,
- duplicate replay response recording,
- replay publication and failed-publish response,
- replay bookkeeping and post-publish bookkeeping failure response.

The route path, request/response contract, deterministic fingerprint inputs, audit statuses,
duplicate-block response, no-correlation response, missing-event response, publish failure response,
and bookkeeping failure response remain unchanged.

## Evidence

Focused route proof:

- `python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_replay_consumer_dlq_event_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_replay_consumer_dlq_event_reports_not_replayable_without_correlation tests\integration\services\ingestion_service\test_ingestion_routers.py::test_replay_consumer_dlq_event_returns_not_found_for_missing_event tests\integration\services\ingestion_service\test_ingestion_routers.py::test_replay_consumer_dlq_event_blocks_duplicate_replay tests\integration\services\ingestion_service\test_ingestion_routers.py::test_replay_consumer_dlq_event_reports_bookkeeping_failure_after_publish -q`
- Result: `5 passed`

Focused static proof:

- `python -m ruff check src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/event_replay_service/test_ingestion_operations.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/event_replay_service/test_ingestion_operations.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/event_replay_service/app/routers/ingestion_operations.py -s --exclude "*/build/*" | Select-String -Pattern " - [C-F] \("`
- Result: no C-or-worse functions reported in `ingestion_operations.py`

Measured movement:

- `replay_consumer_dlq_event`: `C (18)` -> `A (5)`
- `ingestion_operations.py`: no C-or-worse functions remain

## Residual Risk

This slice does not change replay policy, replay audit persistence schema, Kafka publication
implementation, or ingestion job state transitions. Remaining C-ranked hotspots are outside
`ingestion_operations.py`.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of consumer-DLQ recovery control flow,
- separation of recovery outcomes by audit status,
- direct proof across dry-run, missing-event, no-correlation, duplicate-blocked, and bookkeeping
  failure paths.

It does not claim full bank-buyable readiness for `lotus-core`.
