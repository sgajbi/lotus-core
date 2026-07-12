# CR-1001: Kafka Consumer DLQ Reason Classifier Boundary

Date: 2026-06-05

## Scope

Split shared Kafka consumer DLQ reason-code classification into explicit token groups and focused
text-matching helpers without changing reason-code precedence or DLQ payload semantics.

## Finding

`classify_dlq_reason_code` mixed error text normalization, JSON deserialization precedence,
validation token matching, data-integrity token matching, timeout token matching, authorization
token matching, and unclassified fallback in one C-ranked classifier. Existing direct tests covered
only deserialization and timeout outcomes.

## Action

Added explicit deserialization tokens, ordered reason-code token groups, and focused helpers for
combined error text and token matching. Expanded the unit test taxonomy to cover validation,
data-integrity, timeout, authorization, and unclassified outcomes.

## Result

`classify_dlq_reason_code` improved from `C (12)` to `A (5)`. The extracted classifier helpers are
A-ranked, and `kafka_consumer.py` remains A-ranked maintainability at `A (38.68)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
  => 23 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `classify_dlq_reason_code` `A (5)`, `_combined_error_text` `A (1)`, and
  `_contains_any_token` `A (2)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `kafka_consumer.py` `A (38.68)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_consumer.py`
  => 387 SLOC / 232 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka consumer classifier refactor
that preserves DLQ reason-code taxonomy and payload semantics.
