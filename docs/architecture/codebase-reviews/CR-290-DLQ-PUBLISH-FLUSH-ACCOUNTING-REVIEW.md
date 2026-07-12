# CR-290: DLQ publish flush accounting

Date: 2026-03-14

## Summary
- Hardened `BaseConsumer._send_to_dlq_async(...)` so a positive `flush(timeout=5)` result no longer
  looks like a successful DLQ send.

## Problem
- `_send_to_dlq_async(...)` published the DLQ message, called `flush(timeout=5)`, and then
  immediately recorded the DLQ event in durable storage.
- But `KafkaProducer.flush(...)` can return a positive undelivered count without raising.
- That meant the consumer could:
  - record a DLQ event as if the message had been sent
  - log the message as sent to DLQ
  - even though Kafka had not actually acknowledged delivery

## Change
- Treated positive `flush(timeout=5)` results as an explicit failure:
  - raise a runtime error inside `_send_to_dlq_async(...)`
  - skip `_record_consumer_dlq_event(...)`
  - fall through to the existing fatal log path
- This keeps DLQ storage and logging aligned with actual delivery accounting.

## Why this matters
- DLQ is the last-resort safety path for poison-pill and terminal consumer failures.
- If the app records DLQ success before Kafka has really acknowledged it, operators get a false
  sense of safety during incident handling.
- This fix makes the DLQ path more honest at exactly the point where honesty matters most.

## Evidence
- Unit proofs:
  - `tests/unit/libs/portfolio-common/test_kafka_consumer.py`
  - proves:
    - a positive flush timeout does not record a DLQ event
    - a synchronous publish exception does not record a DLQ event
    - both failure modes still log the fatal DLQ-send failure

## Validation
- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`

## Follow-up
- The next worthwhile step is the same delivery-accounting standard anywhere else the platform
  publishes a “safety” or recovery message and then immediately persists success based only on
  `flush(...)` not raising.
