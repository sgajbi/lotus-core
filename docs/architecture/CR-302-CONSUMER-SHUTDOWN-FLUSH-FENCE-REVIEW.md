# CR-302 Consumer Shutdown Flush Fence Review

## Summary

`BaseConsumer.shutdown()` called:

- `self._consumer.close()`
- `self._producer.flush()`

without any timeout accounting or exception fence.

## Why This Matters

This is shared infrastructure used across many services. During shutdown:

- `close()` can raise
- `flush()` can raise
- `flush()` can also leave undelivered messages without raising

Treating shutdown as unconditional success weakens runtime truth and lets shared shutdown paths
crash or overstate clean completion.

## Change

- fenced `self._consumer.close()` with error logging
- changed producer shutdown flush to:
  - `flush(timeout=5)`
  - log error if undelivered messages remain
  - log error if flush raises
- shutdown now keeps moving even when close/flush misbehaves

## Evidence

- added direct unit proofs in:
  - `tests/unit/libs/portfolio-common/test_kafka_consumer.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
    - `16 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`
    - passed

## Follow-up

- keep applying explicit timeout and exception accounting to any remaining shared shutdown hook
  that still assumes close/flush succeeds silently.
