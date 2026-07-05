# CR-1364 Kafka Producer Runtime Policy

## Objective

Fix GitHub issue #572 by replacing the hard-coded shared Kafka producer profile with a governed,
service-aware runtime policy while preserving the existing durability posture.

## Expected Improvement

- Lower design-time complexity by centralizing producer client identity, batching, timeout,
  compression, retry, and queue-bound configuration in one policy object.
- Lower runtime risk by validating producer timeout and batching relationships before constructing
  the Confluent producer.
- Improve operability by exposing service-specific `client.id` values and queue bounds for Kafka
  diagnostics.
- Preserve reliability by keeping `enable.idempotence=true`, `acks=all`, and
  `max.in.flight.requests.per.connection=5` as adapter-owned invariants.

## Changes

- Added `portfolio_common.kafka_producer_policy.KafkaProducerPolicy`.
- Routed `portfolio_common.kafka_utils.KafkaProducer` through the shared policy.
- Added default env controls:
  - `LOTUS_CORE_KAFKA_PRODUCER_CLIENT_ID`
  - `LOTUS_CORE_KAFKA_PRODUCER_RETRIES`
  - `LOTUS_CORE_KAFKA_PRODUCER_LINGER_MS`
  - `LOTUS_CORE_KAFKA_PRODUCER_BATCH_NUM_MESSAGES`
  - `LOTUS_CORE_KAFKA_PRODUCER_COMPRESSION_TYPE`
  - `LOTUS_CORE_KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS`
  - `LOTUS_CORE_KAFKA_PRODUCER_REQUEST_TIMEOUT_MS`
  - `LOTUS_CORE_KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_MESSAGES`
  - `LOTUS_CORE_KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_KBYTES`
  - `LOTUS_CORE_KAFKA_PRODUCER_DEFAULTS_JSON`
  - `LOTUS_CORE_KAFKA_PRODUCER_SERVICE_OVERRIDES_JSON`
- Made the producer singleton cache service-name and bootstrap-server aware.
- Updated repo context and the operations runbook.

## Tests Added

- Default producer config preserves prior hard-coded values and durable invariants.
- Service-specific producer identity defaults to `<service_name>-producer`.
- Default JSON and service-specific JSON overrides are applied.
- Invalid timeout relationships fail fast with `RuntimeConfigurationError`.
- Strict invalid batch size fails at startup.
- Unsupported override keys, including attempts to override idempotence, are rejected.
- Reset closes every cached service-specific producer.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_kafka_utils.py -q
python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_utils.py src\libs\portfolio-common\portfolio_common\kafka_producer_policy.py tests\unit\libs\portfolio-common\test_kafka_utils.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_utils.py src\libs\portfolio-common\portfolio_common\kafka_producer_policy.py tests\unit\libs\portfolio-common\test_kafka_utils.py
```

Final slice gates are recorded in the commit and issue comment.

## Downstream Compatibility Impact

Existing callers can continue using `KafkaProducer()` and `get_kafka_producer()` without arguments.
Default producer values preserve the previous profile for `client.id`, retry count, linger, batch
size, compression, delivery timeout, and request timeout. The new queue bounds are explicit and use
the conventional librdkafka default posture.

The intentional behavior change is that invalid producer override keys and invalid timeout
relationships fail before producer construction instead of being silently accepted.

## Docs, Context, And Skill Decision

- Repo context updated with the shared producer-policy rule.
- Operations runbook updated with supported producer env controls.
- No wiki source update is required because no operator workflow page changed.
- No platform skill update is required in this slice: `lotus-backend-delivery-governance` already
  requires fixing concrete Kafka producer coupling through a shared port/adapter/policy pattern.

## Remaining Hotspots

Issue #573 should handle explicit publish back-pressure and local queue saturation behavior on top
of this policy. This slice makes queue bounds configurable but does not change publish failure
classification or retry semantics.
