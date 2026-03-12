# CR-148 - DLQ Correlation Header Normalization Review

## Scope
- `src/libs/portfolio-common/portfolio_common/kafka_consumer.py`
- `tests/unit/libs/portfolio-common/test_kafka_consumer.py`

## Finding
The shared Kafka consumer DLQ path still treated the default ambient sentinel `"<not-set>"` as if it were a real correlation id. That leaked into the DLQ payload and emitted an empty `correlation_id` header on the wire.

This was inconsistent with the normalization already applied across replay, ingestion, scheduler dispatch, and other direct publication paths.

## Fix
- Normalize `"<not-set>"` to `None` before constructing the DLQ payload.
- Emit a Kafka `correlation_id` header only when a real correlation id is present.
- Add unit proof for both the correlated and uncorrelated DLQ paths.

## Result
Consumer DLQ emission now follows the same lineage contract as the rest of the platform: missing correlation stays missing instead of becoming an empty transport artifact.
