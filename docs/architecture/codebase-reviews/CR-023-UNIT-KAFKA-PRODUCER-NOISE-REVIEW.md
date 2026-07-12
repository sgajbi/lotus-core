# CR-023 Unit Kafka Producer Noise Review

## Scope

Remove noisy librdkafka connection-failure output from the unit-test tier.

## Findings

The unit manifest was green, but it still printed repeated stderr lines from a
real `confluent_kafka.Producer` background thread:

- `portfolio-analytics-producer ... Connect to localhost:<port> failed ...`

This was test-harness noise, not a failing assertion. The problem was that unit
tests still allowed accidental construction of the real producer class in paths
that did not explicitly patch `portfolio_common.kafka_utils.Producer`.

The tier contract for unit tests is clear: they should never depend on a real
Kafka client or broker.

## Actions Taken

1. Added a unit-tier autouse fixture in `tests/unit/conftest.py` that:
   - monkeypatches `portfolio_common.kafka_utils.Producer` to a `MagicMock`
   - resets the cached producer singleton before and after each unit test
2. Added explicit producer shutdown support in
   `portfolio_common.kafka_utils.reset_kafka_producer(...)` / `close(...)`
   so the singleton can be torn down deterministically when needed
3. Re-ran the full unit manifest to confirm the suite is now both green and
   quiet
4. Removed stale legacy `__pycache__` directories under:
   - `tests/unit/libs/risk-analytics-engine`
   - `tests/unit/libs/concentration_analytics_engine`
   - `tests/unit/libs/performance-calculator-engine`

## Result

The unit tier now enforces the correct contract:

- no real Kafka producer construction in unit tests
- no noisy librdkafka background-thread stderr during the unit manifest

## Follow-up

If a test truly needs a real Kafka client, it belongs in integration coverage,
not the unit tier.
