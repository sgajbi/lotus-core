# CR-1365 Kafka Producer Back-Pressure

## Objective

Fix GitHub issue #573 by making Kafka local queue saturation observable and explicitly classified
without changing the existing scheduler, outbox, or replay dispatch contracts.

## Existing Contract Preserved

The shared `KafkaEventPublisher` already distinguishes producer outcomes:

- successful publish acceptance returns `EventPublishStatus.SUCCESS`;
- `BufferError` returns retryable `KafkaPublishBackPressure`;
- generic publish exceptions return terminal `KafkaPublishFailed`;
- flush timeouts or flush exceptions return uncertain `KafkaPublishUncertain`.

Valuation and aggregation dispatch code already raises `SchedulerDispatchError` on publish or
confirmation failure and recovers remaining jobs instead of marking them dispatched.

## Changes

- Added shared producer telemetry metric `kafka_producer_events_total` with bounded labels
  `service`, `topic`, `outcome`, and `reason`.
- Emitted producer outcomes from `KafkaProducer.publish_message`:
  - `accepted` / `produce_queued`
  - `back_pressure` / `queue_full`
  - `failed` / `producer_publish_error`
- Logged local queue saturation as `kafka.producer.back_pressure` with reason `queue_full`.
- Added tests for accepted publish telemetry, queue-full telemetry/logging, generic failure
  telemetry, and flush-exception uncertain delivery.
- Updated repo context and the operations runbook.

## Expected Improvement

- Runtime complexity is reduced because queue saturation is now handled once in the shared producer
  adapter and surfaced through the existing publisher port contract.
- Operators get a direct, low-cardinality metric for producer queue saturation.
- Application callers can keep treating back-pressure as retryable/deferred work rather than
  parsing exception text.

## Tests Added

- `KafkaProducer.publish_message` records accepted produce events.
- `KafkaProducer.publish_message` records queue-full back-pressure and logs a bounded event.
- `KafkaProducer.publish_message` records generic publish failures separately from queue-full.
- `KafkaEventPublisher.confirm_delivery` maps flush exceptions to uncertain delivery.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_kafka_utils.py tests\unit\libs\portfolio-common\test_event_publisher.py -q
python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_utils.py src\libs\portfolio-common\portfolio_common\monitoring.py tests\unit\libs\portfolio-common\test_kafka_utils.py tests\unit\libs\portfolio-common\test_event_publisher.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_utils.py src\libs\portfolio-common\portfolio_common\monitoring.py tests\unit\libs\portfolio-common\test_kafka_utils.py tests\unit\libs\portfolio-common\test_event_publisher.py
make metric-vocabulary-guard
```

Final slice gates are recorded in the commit and issue comment.

## Downstream Compatibility Impact

No route path, DTO, OpenAPI schema, database schema, Kafka topic, Kafka payload, or scheduler public
contract changed. `BufferError` still propagates from `KafkaProducer` so `KafkaEventPublisher` can
map it to retryable back-pressure. Existing callers that directly call `KafkaProducer` receive the
same exception type with better logs and metrics.

## Docs, Context, And Skill Decision

- Repo context updated with the shared back-pressure contract.
- Operations runbook updated with producer metric and queue-saturation guidance.
- No wiki source update is required because no separate wiki operator workflow changed.
- No platform skill update is required in this slice; the existing backend delivery guidance
  already requires shared adapter/port handling for concrete Kafka producer behavior.

## Remaining Hotspots

Direct legacy `KafkaProducer` callers still exist for transitional replay/outbox paths. They now
receive explicit producer telemetry, but broader migration to the shared `EventPublisher` port
remains part of the existing architecture-boundary backlog.
