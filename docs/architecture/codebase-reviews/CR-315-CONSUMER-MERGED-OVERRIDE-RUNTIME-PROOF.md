# CR-315 Consumer Merged Override Runtime Boundary Proof

## Scope
Shared Kafka consumer runtime override application.

## Finding
`CR-314` fenced invalid heartbeat/session relationships at the merged config helper boundary, but there was still no proof that the shared `BaseConsumer` runtime path preserved that fence when applying overrides into `_consumer_config`.

## Fix
Added a direct unit proof on `BaseConsumer` construction showing that:
- merged `session.timeout.ms` from defaults is applied
- invalid merged `heartbeat.interval.ms` from group overrides is dropped
- the consumer keeps its safe built-in heartbeat default instead of inheriting the invalid merged value

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`
