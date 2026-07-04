# CR-1308 Event Publisher Ports

## Scope

Issue cluster: GitHub issue #653.

This slice introduces a shared event-publisher port and rewires representative ingestion and
valuation publishing paths away from direct Kafka producer dependencies.

## Objective

Reduce application and scheduler coupling to concrete Kafka utilities while preserving existing
topic, key, payload, header, failure, and flush behavior.

## Changes

1. Added `portfolio_common.event_publisher` with `EventPublisher`, `EventPublishRequest`,
   `EventPublishResult`, and `EventPublishStatus`.
2. Added `KafkaEventPublisher` as the concrete Kafka adapter.
3. Rewired `IngestionService` to accept `EventPublisher` and publish via `EventPublishRequest`.
4. Rewired `get_ingestion_service` to depend on `get_kafka_event_publisher`.
5. Rewired `KafkaValuationJobPublisher` to use the shared event-publisher port instead of direct
   Kafka producer calls.
6. Added direct publisher-result tests for success, retryable failure, terminal failure, and
   uncertain flush behavior.
7. Added fake/wrapped-publisher coverage for ingestion topic/key/payload/header propagation,
   idempotency/correlation/trace headers, batch failure accounting, reprocessing flush failure, and
   valuation scheduler dispatch behavior.
8. Added `scripts/event_publisher_port_guard.py`, wired it into `make architecture-guard`, and
   documented the event publisher port standard.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, Kafka key, Kafka header,
event payload field, idempotency behavior, correlation propagation, metric name, batch failure
message, published-record count, flush timeout error, valuation scheduler recovery behavior, or
database schema changed.

This is design modularity inside existing deployables, not a runtime service split.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/libs/portfolio-common/test_event_publisher.py tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py tests/unit/scripts/test_event_publisher_port_guard.py -q`
   - 49 passed, 1 existing Pydantic serialization warning in an empty-partition-key test.
2. `python scripts/event_publisher_port_guard.py`
   - Passed.
3. Scoped Ruff lint passed.
4. Scoped Ruff format passed.

Final architecture guard, wiki/docs gate, and diff evidence are recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger, repo-local engineering context, and event publisher port
standard.

No wiki update is required because this slice changes internal application-to-infrastructure
composition and testability, not operator commands, route behavior, supported features, or
published wiki truth.

No central Lotus skill change is required.

## Remaining Work

GitHub issue #653 is locally fixed for representative ingestion and scheduler publisher-port
acceptance criteria pending PR CI/QA and issue closure.

Follow-up slices should move outbox dispatcher publication, aggregation scheduler publication,
reprocessing repository publication, and runtime consumer-manager publisher composition onto the
shared event-publisher port where it reduces coupling without hiding delivery semantics.

