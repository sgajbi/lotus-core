# CR-307 Kafka Producer Close Flush Truth Review

## Summary

`KafkaProducer.close()` flushed and discarded the underlying producer with no timeout accounting
or exception fence.

## Why This Matters

This wrapper is shared across the platform. During producer shutdown:

- `flush(timeout)` can leave undelivered messages without raising
- `flush(timeout)` can also raise

Silently discarding the producer after those outcomes overstates clean shutdown and hides useful
operator evidence.

## Change

- fenced `KafkaProducer.close()` around `flush(timeout)`
- now:
  - logs error when undelivered messages remain
  - logs error when flush raises
  - still clears the producer reference in all cases

## Evidence

- added direct unit proofs in:
  - `tests/unit/libs/portfolio-common/test_kafka_utils.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_kafka_utils.py -q`
    - `7 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_utils.py tests/unit/libs/portfolio-common/test_kafka_utils.py`
    - passed

## Follow-up

- if we want stronger operator evidence later, the next step is surfacing where shared producer
  shutdown happens without a surrounding service logger or lifecycle breadcrumb.
