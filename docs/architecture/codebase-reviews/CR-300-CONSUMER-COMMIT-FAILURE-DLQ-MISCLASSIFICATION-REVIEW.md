# CR-300 Consumer Commit Failure DLQ Misclassification Review

## Summary

`BaseConsumer.run()` handled `process_message(...)` and synchronous offset commit inside the same
`try` block. If processing succeeded but `self._consumer.commit(...)` raised, the code fell into
the terminal-processing failure path and attempted to send the message to DLQ.

## Why This Matters

A Kafka commit failure is not evidence that the message payload is poison or invalid. Treating it
as a terminal processing error can:

- send an already-processed message to DLQ incorrectly
- create false operator evidence that the message itself failed validation or business handling
- mix broker/commit instability with poison-pill handling

This is a shared-runtime correctness bug because `BaseConsumer` is reused across many services.

## Change

- Split the run-loop success path into:
  - message processing
  - offset commit
- commit now happens in the `else` branch after successful processing
- if commit raises:
  - log a warning with topic, consumer group, key, and commit error
  - do not send to DLQ
  - do not mark the message as successfully processed for metrics
  - leave the offset uncommitted so Kafka can redeliver

## Evidence

- Added unit proof in:
  - `tests/unit/libs/portfolio-common/test_kafka_consumer.py`
- Validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
    - `13 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`
    - passed

## Follow-up

- Review whether any higher-level consumer wrapper still conflates broker/commit failures with
  terminal business-message failures after this base-runtime fix.
