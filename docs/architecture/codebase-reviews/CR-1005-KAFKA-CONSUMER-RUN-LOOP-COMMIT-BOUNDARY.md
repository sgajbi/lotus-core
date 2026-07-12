# CR-1005: Kafka Consumer Run Loop Commit Boundary

Date: 2026-06-05

## Scope

Split shared Kafka consumer run-loop offset commit handling into focused successful-processing,
successful-DLQ-publication, DLQ-publication-failure, and commit log-context helpers without
changing successful offset commits, DLQ-success commits, retryable-error non-commit behavior,
DLQ-failure non-commit behavior, commit-failure logging, processed metrics accounting, or
correlation context reset behavior.

## Finding

`BaseConsumer.run` mixed polling, Kafka error handling, correlation setup, sync/async message
dispatch, retryable error handling, terminal DLQ routing, offset commit after DLQ publication,
DLQ-publication-failure logging, offset commit after successful processing, commit-failure logging,
metrics recording, and context reset in one C-ranked method. The offset commit policy repeated
message log context construction and direct consumer commit calls across both successful processing
and successful DLQ publication paths.

## Action

Added focused helpers for commit after DLQ publication, commit after successful processing,
DLQ-publication-failure logging, commit-failure log context, and message log context. Existing
run-loop tests continue to cover successful processing commits, successful DLQ commits,
DLQ-publication failure non-commit behavior, retryable non-commit behavior, and commit-failure
logging.

## Result

`BaseConsumer.run` improved from `C (18)` to `C (13)`. The extracted commit-policy helpers are
A-ranked, and `kafka_consumer.py` remains A-ranked maintainability at `A (31.23)`. The run loop
remains a C-ranked orchestration hotspot and should be reduced further in a separate slice.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
  => 28 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py tests\unit\libs\portfolio-common\test_kafka_consumer.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `run` `C (13)`, `_commit_after_dlq_publication` `A (2)`,
  `_commit_after_successful_processing` `A (2)`, `_log_dlq_publication_failed` `A (1)`,
  `_commit_failure_log_context` `A (1)`, and `_message_log_context` `A (1)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
  => `kafka_consumer.py` `A (31.23)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_consumer.py`
  => 463 SLOC / 275 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared Kafka consumer run-loop commit-policy
refactor that preserves offset commit and non-commit semantics.
