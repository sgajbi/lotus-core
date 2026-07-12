# CR-291: DLQ commit gating

Date: 2026-03-14

## Summary
- Hardened the base consumer loop so terminal-message offsets are committed only after DLQ
  publication actually succeeds.

## Problem
- `BaseConsumer.run()` treated terminal processing errors as:
  - send to DLQ
  - commit offset
- But `_send_to_dlq_async(...)` swallowed DLQ publication failure and only logged it.
- That meant the base consumer could:
  - fail processing
  - fail to publish to DLQ
  - still commit the original offset
- That is a real message-loss path.

## Change
- Changed `_send_to_dlq_async(...)` to return `True` on successful DLQ send and `False` on failure.
- Updated `BaseConsumer.run()` so terminal-message offsets are committed only when DLQ send
  succeeded.
- If DLQ send fails, the consumer now logs a warning and leaves the offset uncommitted so Kafka can
  redeliver the message.

## Why this matters
- This is base-runtime correctness, not just better logging.
- The previous behavior could permanently lose a terminal message during the exact moment the safety
  path was also failing.
- The new behavior preserves recoverability:
  - either the message reaches DLQ and we commit
  - or DLQ publication fails and Kafka redelivers

## Evidence
- Unit proofs:
  - `tests/unit/libs/portfolio-common/test_kafka_consumer.py`
  - proves:
    - terminal failure with successful DLQ send still commits
    - terminal failure with failed DLQ send does not commit
    - `_send_to_dlq_async(...)` now returns explicit success/failure truth

## Validation
- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`

## Follow-up
- This closes the major base-consumer safety gap.
- The next worthwhile move is to review any caller or wrapper that still assumes a logged recovery
  action implies durable success without checking whether the publish path actually succeeded.
