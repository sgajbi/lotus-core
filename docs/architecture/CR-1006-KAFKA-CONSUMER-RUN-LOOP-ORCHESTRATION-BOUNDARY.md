# CR-1006: Kafka Consumer Run Loop Orchestration Boundary

Date: 2026-06-05

## Scope

Split shared Kafka consumer run-loop orchestration into focused poll-error handling,
per-message processing, sync/async dispatch, terminal-error handling, retryable-error logging, and
metrics helpers without changing polling cadence, fatal-error shutdown behavior, non-fatal-error
skip behavior, correlation setup/reset, sync or async `process_message(...)` dispatch, retryable
non-commit behavior, DLQ terminal-error routing, offset commit semantics, or processing metrics.

## Finding

After CR-1005, `BaseConsumer.run` still owned polling, Kafka error handling, valid-message
processing, terminal/retryable error handling, metrics, and correlation reset in one C-ranked
orchestration method. Poll-error behavior also lacked direct unit tests for fatal and non-fatal
consumer errors.

## Action

Added focused helpers for polled-message error handling, fatal and non-fatal consumer-error
logging, per-message processing, sync/async message dispatch, retryable processing-error logging,
terminal processing-error handling, processing metrics, and metric labels. Added direct run-loop
tests for fatal consumer errors stopping without processing and non-fatal consumer errors skipping
the errored message before processing the next valid message.

## Result

`BaseConsumer.run` improved from `C (13)` to `A (5)`, and `_process_polled_message` reports
`A (4)`. The touched run-loop orchestration helpers are A-ranked, and `kafka_consumer.py` remains
A-ranked maintainability at `A (28.49)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
  => 30 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `run` `A (5)`, `_process_polled_message` `A (4)`, `_should_skip_polled_message` `A (3)`,
  `_dispatch_message_for_processing` `A (2)`, `_handle_terminal_processing_error` `A (2)`,
  `_record_processing_metrics` `A (3)`, `_handle_fatal_consumer_error` `A (1)`,
  `_handle_nonfatal_consumer_error` `A (1)`, `_log_retryable_processing_error` `A (1)`, and
  `_metric_labels` `A (1)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `kafka_consumer.py` `A (28.49)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_consumer.py`
  => 491 SLOC / 297 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka consumer run-loop refactor that
preserves poll, dispatch, commit, DLQ, metrics, and correlation semantics.
