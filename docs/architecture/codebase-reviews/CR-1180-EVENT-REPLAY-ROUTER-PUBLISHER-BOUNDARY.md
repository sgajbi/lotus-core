# CR-1180 Event Replay Router Publisher Boundary

## Objective

Address GitHub issue #639 by removing concrete Kafka publishing dependencies from the event replay
API router and moving replay payload dispatch behind an application-layer boundary.

## Expected Improvement

- Event replay route handlers no longer import `KafkaProducer` or `get_kafka_producer`.
- Retry and consumer-DLQ replay handlers depend on a `ReplayPayloadDispatcher` application
  protocol instead of a concrete Kafka utility.
- Replay payload endpoint-to-publisher mapping is testable without FastAPI route wiring.
- `make architecture-guard` now blocks reintroducing concrete Kafka utility imports in event
  replay routers.

## Changes

- Added `src/services/event_replay_service/app/application/replay_payload_dispatcher.py`.
- Moved replay payload publisher descriptors and ingestion DTO validation into the application
  dispatcher module.
- Added `get_replay_payload_dispatcher(...)` router composition for the existing
  `IngestionService` backed dispatcher.
- Updated ingestion job retry and consumer-DLQ replay routes to pass the dispatcher through their
  existing workflow helpers.
- Extended `scripts/architecture_boundary_guard.py` with an event-replay router Kafka-import rule.
- Updated focused tests to exercise dispatcher publish mapping and architecture-rule enforcement.

## Compatibility

No route path, request DTO, response DTO, OpenAPI status code, Kafka topic, durable audit row,
database schema, idempotency behavior, duplicate-blocking behavior, dry-run behavior, or failure
mapping changed. Runtime publishing still flows through the existing `IngestionService` and Kafka
producer adapter; only the API-layer dependency direction changed.

## Validation

- `python -m pytest tests/unit/services/event_replay_service/test_ingestion_operations.py tests/unit/scripts/test_architecture_boundary_guard.py -q`
- `python -m pytest tests/unit/services/event_replay_service/test_ingestion_operations.py tests/unit/scripts/test_architecture_boundary_guard.py tests/integration/services/event_replay_service/test_event_replay_app.py -q`
- `make architecture-guard`
- `make quality-import-boundary-gate`
- `python -m ruff check src/services/event_replay_service/app/application/replay_payload_dispatcher.py src/services/event_replay_service/app/routers/ingestion_operations.py scripts/architecture_boundary_guard.py tests/unit/services/event_replay_service/test_ingestion_operations.py tests/unit/scripts/test_architecture_boundary_guard.py`
- `python -m ruff format --check src/services/event_replay_service/app/application/replay_payload_dispatcher.py src/services/event_replay_service/app/routers/ingestion_operations.py scripts/architecture_boundary_guard.py tests/unit/services/event_replay_service/test_ingestion_operations.py tests/unit/scripts/test_architecture_boundary_guard.py`
- `git diff --check`

## Documentation And Wiki Decision

Updated the codebase review ledger, this CR evidence note, and quality scorecard/health report
because architecture guard truth changed. No wiki source update is required because no supported
operator workflow, API contract, or publication-facing documentation changed.

## Follow-Up

Issue #639 should remain open until PR/CI evidence is available. Follow-up architecture slices
should move the remaining retry and DLQ replay workflow orchestration out of the router into
application command handlers with explicit job-service and audit ports.
