# CR-1004: Kafka Consumer Shutdown Boundary

Date: 2026-06-05

## Scope

Split shared Kafka consumer shutdown handling into focused wakeup, close, DLQ producer flush, and
shutdown log-context helpers without changing `_running` state updates, consumer wakeup behavior,
consumer close behavior, DLQ producer flush timeout handling, failure logging, or final close log
semantics.

## Finding

`BaseConsumer.shutdown` mixed shutdown state mutation, consumer wakeup discovery, wakeup failure
logging, consumer close, close failure logging, DLQ producer flush, undelivered-message logging,
flush exception logging, and final shutdown logging in one B-ranked method. Existing tests covered
flush timeout logging and normal wakeup-before-close behavior, but not wakeup or close failure
handling.

## Action

Added focused helpers for shutdown log context, consumer wakeup, consumer close, and DLQ producer
flush. Added direct tests proving shutdown still closes the consumer after wakeup failure and logs
close failure without raising.

## Result

`BaseConsumer.shutdown` improved from `B (8)` to `A (3)`. The extracted shutdown helpers are
A-ranked, and `kafka_consumer.py` remains A-ranked maintainability at `A (31.86)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
  => 28 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `shutdown` `A (3)`, `_shutdown_log_context` `A (1)`,
  `_wakeup_consumer_for_shutdown` `A (4)`, `_close_consumer_for_shutdown` `A (3)`, and
  `_flush_dlq_producer_for_shutdown` `A (4)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `kafka_consumer.py` `A (31.86)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_consumer.py`
  => 462 SLOC / 265 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka consumer shutdown refactor that
preserves wakeup, close, DLQ producer flush, and failure logging semantics.
