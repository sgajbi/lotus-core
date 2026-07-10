# CR-1483: Committed Kafka Partition Lag

Date: 2026-07-10
Issue: #468
Status: Hardened locally; dashboard and deployed evidence pending

## Objective

Expose bounded, low-overhead consumer lag for the combined live and replay groups without adding a
broker query to transaction processing or allowing telemetry failure to change financial outcomes.

## Change

`BaseConsumer` now records:

`kafka_consumer_partition_lag_messages{service,topic,group_id,partition}`

The observation occurs only after a successful synchronous offset commit, using the Confluent
consumer's cached partition high watermark. Lag is calculated as:

`max(0, high_watermark - committed_message_offset - 1)`

The partition label is a bounded Kafka topology dimension and is registered in the shared metric
vocabulary. Business IDs, message keys, offsets, correlation IDs, and error text remain excluded.

## Correctness And Performance

- No broker round trip is introduced because `get_watermark_offsets(..., cached=True)` is required.
- A failed offset commit does not advance the gauge.
- Invalid or unavailable cached watermark data is ignored.
- Metric collection failure is isolated and cannot change commit success or message processing.
- Successful DLQ commits also update lag because those offsets have intentionally advanced.

## Compatibility

No topic, payload, group, offset, retry, DLQ, API, database, or deployed-topology contract changed.
The metric is additive and automatically separates the final live and replay consumers by their
existing group IDs.

## Validation

- shared Kafka/monitoring/runtime/worker pack: `83 passed`;
- metric label and exact lag arithmetic proof;
- cached-watermark call proof;
- telemetry failure non-interference proof;
- metric vocabulary, observability contract, MyPy, and full Ruff lint/format gates passed.

Prometheus alert thresholds and deployed lag-recovery evidence remain cutover prerequisites.
