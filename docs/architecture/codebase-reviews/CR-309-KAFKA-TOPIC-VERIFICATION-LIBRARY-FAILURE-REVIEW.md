# CR-309 Kafka Topic Verification Library Failure Review

## Summary

`ensure_topics_exist(...)` lived in shared library code but called `sys.exit(1)` on unexpected
errors while verifying Kafka metadata.

## Why This Matters

A shared infrastructure helper should raise a typed failure and let the service runtime classify
and log it. Calling `sys.exit(1)` inside library code:

- bypasses shared runtime classification
- makes testing and composition harder
- turns one helper into an implicit process terminator

## Change

- introduced `KafkaTopicVerificationError`
- replaced `sys.exit(1)` with typed exception raising on unexpected verification failures
- kept expected missing-topic behavior on the retry path unchanged

## Evidence

- added direct unit proofs in:
  - `tests/unit/libs/portfolio-common/test_kafka_admin.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_kafka_admin.py -q`
    - `3 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_admin.py tests/unit/libs/portfolio-common/test_kafka_admin.py`
    - passed

## Follow-up

- the next worthwhile step would be explicit service-level proof that startup now classifies typed
  topic-verification failure through the shared worker-runtime critical path.
