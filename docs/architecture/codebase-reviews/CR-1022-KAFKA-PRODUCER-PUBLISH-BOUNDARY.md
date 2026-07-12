# CR-1022: Kafka Producer Publish Boundary

Date: 2026-06-05

## Scope

Reduce shared Kafka producer publish complexity while preserving JSON serialization, key encoding,
header copying, outbox-id header insertion, delivery-report success/failure logging, outbox-id
fallback from message headers, delivery callback invocation, callback exception logging, producer
polling, and production error propagation.

## Finding

`KafkaProducer.publish_message` mixed publish precondition checks, JSON serialization, header
normalization, outbox-id header mutation, nested delivery callback construction, outbox-id recovery
from message headers, delivery failure logging, delivery success logging, delivery callback
invocation, callback failure handling, key encoding, produce invocation, polling, and production
exception logging in one B-ranked method.

## Action

Added focused helpers for publish-header construction, key encoding, delivery-report callback
construction, outbox-id extraction/decoding, delivery failure handling, delivery success handling,
delivery log context, message-key representation, and guarded delivery-callback notification.

## Result

`KafkaProducer.publish_message` improved from `B (6)` to `A (3)`. Every function/class/method in
`kafka_utils.py` now reports A-ranked cyclomatic complexity, and the module remains A-ranked
maintainability at `A (57.38)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_utils.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_utils.py tests\unit\libs\portfolio-common\test_kafka_utils.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\kafka_utils.py tests\unit\libs\portfolio-common\test_kafka_utils.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_utils.py -s`
  => `KafkaProducer.publish_message` `A (3)` and every function/class/method A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_utils.py -s`
  => `kafka_utils.py` `A (57.38)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_utils.py`
  => 186 SLOC / 112 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka producer refactor that
preserves existing publish and delivery callback behavior.
