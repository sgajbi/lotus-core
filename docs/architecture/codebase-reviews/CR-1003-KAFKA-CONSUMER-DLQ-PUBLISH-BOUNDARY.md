# CR-1003: Kafka Consumer DLQ Publish Boundary

Date: 2026-06-05

## Scope

Split shared Kafka consumer DLQ publication into focused payload, header, publish, delivery
confirmation, and key-decoding helpers without changing DLQ topic selection, payload fields,
correlation header propagation, producer flush behavior, persisted DLQ audit recording, success
logging, or fatal failure handling.

## Finding

`BaseConsumer._send_to_dlq_async` mixed metric accounting, producer availability checks,
correlation normalization, reason-code classification, DLQ payload assembly, DLQ header assembly,
producer publish, delivery confirmation, persisted DLQ audit recording, success logging, and fatal
failure handling in one B-ranked method. That made the operational DLQ path harder to review even
though existing tests covered payload shape, missing correlation headers, flush timeout behavior,
publish failure behavior, and audit recording.

## Action

Added focused helpers for DLQ payload construction, DLQ header construction, producer publish,
delivery confirmation, and message key decoding. The public async method remains the orchestration
boundary for metrics, producer guard, audit persistence, success logging, and fatal error fallback.

## Result

`BaseConsumer._send_to_dlq_async` improved from `B (10)` to `A (5)`. The extracted DLQ publication
helpers are A-ranked, and `kafka_consumer.py` remains A-ranked maintainability at `A (34.02)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
  => 26 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `_send_to_dlq_async` `A (5)`, `_build_dlq_payload` `A (1)`, `_build_dlq_headers` `A (3)`,
  `_publish_dlq_message` `A (4)`, `_confirm_dlq_delivery` `A (3)`, and `_message_key_text` `A (2)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `kafka_consumer.py` `A (34.02)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_consumer.py`
  => 454 SLOC / 252 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka consumer DLQ publication
refactor that preserves DLQ payload, header, flush, audit, and failure semantics.
