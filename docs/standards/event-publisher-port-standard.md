# Event Publisher Port Standard

Application services, schedulers, and use cases that publish events must depend on a publisher port
instead of concrete Kafka producer APIs.

## Required Contract

Use `portfolio_common.event_publisher` for representative application publishing paths:

1. `EventPublishRequest` defines topic, partition key, payload, headers, optional outbox id, and
   optional delivery callback.
2. `EventPublishResult` defines delivery status:
   - `success`
   - `retryable_failure`
   - `terminal_failure`
   - `uncertain`
3. `EventPublisher.publish(...)` returns a result instead of leaking concrete producer exceptions
   into application orchestration.
4. `EventPublisher.confirm_delivery(...)` returns a result so application code can distinguish
   confirmed success from uncertain flush or delivery state.

## Application Mapping

Application services still own workflow-specific error mapping. For example, ingestion publish
paths map non-success publish results back to `IngestionPublishError` with the existing failed
record keys and published-record count.

## Concrete Adapter Boundary

`KafkaEventPublisher` is the concrete Kafka adapter. It maps:

1. successful `publish_message(...)` calls to `success`,
2. `BufferError` to `retryable_failure`,
3. unexpected synchronous publish exceptions to `terminal_failure`,
4. non-zero or failed flushes to `uncertain`.

## Enforcement

`make architecture-guard` runs `scripts/event_publisher_port_guard.py`. The guard blocks governed
ingestion and valuation application publisher paths from importing `KafkaProducer` or
`get_kafka_producer` directly.

Existing runtime dispatchers and consumer managers remain separate runtime-composition slices.

