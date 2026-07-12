# CR-1262 Retryable Consumer Failure Budget

Date: 2026-07-01

## Scope

Fix GitHub issue #592 for shared Kafka consumer retryable-failure exhaustion and terminal recovery.

## Finding

`BaseConsumer` treated `RetryableConsumerError` as an intentionally non-terminal failure and left
the offset uncommitted so Kafka could redeliver. That preserved transient dependency recovery, but
there was no shared policy that eventually transitioned a repeatedly retryable message to a
terminal recovery path when the condition persisted.

## Action Taken

Added configurable retryable failure budgets:

- `KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS=0` keeps existing behavior.
- `KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS=0` keeps existing behavior.
- Positive values track retryable failures by deterministic message identity:
  topic/group/partition/offset/key.
- Non-exhausted retryable failures remain uncommitted and redeliver.
- Attempt or elapsed-budget exhaustion logs
  `kafka.consumer.retryable_failure_budget_exhausted`, then routes the message through the existing
  DLQ path.
- If DLQ publication succeeds, the consumer commits the offset and clears retryable/DLQ failure
  attempts.
- If DLQ publication fails, the CR-1261 DLQ publication failure budget controls whether the
  consumer continues redelivery or fails fast.
- Successful processing clears prior retryable failure attempts.

## Compatibility

Default runtime behavior is preserved because both retryable budgets default to disabled (`0`).

No API route, OpenAPI schema, Kafka topic, event payload, database schema, DLQ payload shape,
successful processing behavior, or consumer group changed. The intentional opt-in behavior change
is terminal DLQ recovery for repeatedly retryable messages when operators configure an attempt or
elapsed budget.

## Tests Added

Extended `tests/unit/libs/portfolio-common/test_kafka_consumer.py` with direct run-loop coverage
for:

1. default retryable no-commit behavior tracking attempts,
2. max-attempt exhaustion sending to DLQ and committing after DLQ success,
3. max-elapsed exhaustion sending to DLQ and committing after DLQ success.

Extended `tests/unit/libs/portfolio-common/test_config.py` with environment parsing coverage for
valid and invalid retryable failure budget values.

## Validation

Focused behavior proof:

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py -q`
- Result: `72 passed`

Static proof:

- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py`
- Result: passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py`
- Result: `4 files already formatted`

Measured quality proof:

- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s -a`
- Result: retryable budget helpers are A-ranked; average complexity remains A.
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
- Result: module maintainability remains `B (10.33)`.

## Documentation And Wiki Decision

Updated the operations runbook, repository context, codebase review ledger, quality scorecard, and
refactor health report because the slice adds operator-visible runtime settings and shared consumer
failure policy. No repo-local wiki source page changed in this slice.

Wiki publication check:

- `..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed on pre-existing published-wiki drift for `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, and `Outbox-Events.md`; no repo-local wiki
  source page changed in CR-1262.

## Boundary

The retry budget is deterministic and per-process. Exhaustion evidence becomes durable when the
message is published to the existing DLQ path. Cross-restart durable retry-attempt state would
require a dedicated consumer attempt store and is intentionally left as a future enhancement rather
than implied by this shared-library slice.

## Bank-Buyable Control Movement

This slice improves:

1. bounded retry behavior for shared Kafka consumers,
2. partition-unblocking behavior after repeated retryable failure,
3. explicit max-attempt and max-elapsed policy knobs,
4. source-safe fleet observability for retry exhaustion,
5. reuse of the existing DLQ recovery path rather than service-local retry loops.
