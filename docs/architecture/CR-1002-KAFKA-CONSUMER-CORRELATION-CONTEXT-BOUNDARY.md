# CR-1002: Kafka Consumer Correlation Context Boundary

Date: 2026-06-05

## Scope

Split shared Kafka consumer message-correlation context selection into focused resolution and
precedence helpers without changing current-context preservation, header selection, fallback
selection, fallback-preference behavior, generated correlation fallback, or context reset behavior.

## Finding

`BaseConsumer._message_correlation_context` mixed current context inspection, unset-context
normalization, header lookup, fallback preference, header-vs-fallback precedence, generated
correlation fallback, context variable setting, yielded value selection, and reset handling in one
B-ranked context manager. Existing tests covered DLQ payload propagation, but not the direct
correlation precedence rules used by consumers that call `process_message(...)` outside the main
`run()` loop.

## Action

Added focused helpers for context correlation resolution and header/fallback selection. Added direct
unit tests proving existing-context preservation, header-before-fallback precedence, and
`prefer_fallback=True` behavior.

## Result

`BaseConsumer._message_correlation_context` improved from `B (7)` to `A (3)`. The extracted
correlation selection helpers are A-ranked, and `kafka_consumer.py` remains A-ranked
maintainability at `A (37.37)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
  => 26 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `_message_correlation_context` `A (3)`, `_resolve_context_correlation_id` `A (2)`, and
  `_select_context_correlation_id` `A (5)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `kafka_consumer.py` `A (37.37)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_consumer.py`
  => 415 SLOC / 236 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka consumer context helper refactor
that preserves correlation propagation and reset semantics.
