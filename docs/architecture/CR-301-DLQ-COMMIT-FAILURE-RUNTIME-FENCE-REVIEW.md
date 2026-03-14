# CR-301 DLQ Commit Failure Runtime Fence Review

## Summary

After `CR-300`, successful processing plus commit failure no longer routed a message into DLQ.
But the terminal-error branch still had the same shape:

- processing fails
- DLQ publish succeeds
- offset commit raises

That commit failure escaped the terminal branch directly and could crash the consumer task even
though DLQ publication had already succeeded.

## Why This Matters

Commit failure after successful DLQ publication is broker/runtime instability, not a new terminal
message-classification failure. Letting it crash the consumer task weakens service stability and
makes the failure mode look worse than it is.

## Change

- fenced the commit after successful DLQ publication inside its own `try/except`
- on commit failure:
  - log warning with topic, consumer group, key, and commit error
  - do not re-DLQ the message
  - leave the offset uncommitted for Kafka redelivery
  - continue running instead of crashing the consumer task

## Evidence

- added direct unit proof in:
  - `tests/unit/libs/portfolio-common/test_kafka_consumer.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
    - `14 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`
    - passed

## Follow-up

- keep reviewing remaining consumer runtime paths so broker/commit instability never gets
  flattened into business-message failure semantics or task-wide crashes.
