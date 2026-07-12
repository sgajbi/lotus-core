# CR-303 Consumer Shutdown Wakeup Review

## Summary

`BaseConsumer.run()` polls Kafka with a blocking `poll(1.0)` loop. Even after shutdown is
requested, the consumer can sit inside that poll until the timeout expires.

## Why This Matters

This is shared infrastructure. A one-second delay is not catastrophic, but it is still avoidable
shutdown slack across every service built on `BaseConsumer`. Once shutdown is requested, the base
consumer should actively wake the poll loop rather than waiting for the timeout boundary.

## Change

- `BaseConsumer.shutdown()` now calls `consumer.wakeup()` before `consumer.close()`
- wakeup is fenced with warning logging so shutdown remains bounded even if wakeup itself fails

## Evidence

- added direct unit proof in:
  - `tests/unit/libs/portfolio-common/test_kafka_consumer.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
    - `17 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`
    - passed

## Follow-up

- shared consumer shutdown is now better fenced, but a deeper runtime proof could still be added
  later if we want an integration-level characterization that wakeup shortens teardown in a live
  consumer loop.
