# CR-1261 DLQ Publication Failure Budget

Date: 2026-07-01

## Scope

Fix GitHub issue #593 for shared Kafka consumer DLQ publication failure containment.

## Finding

`BaseConsumer` already avoided message loss by committing terminal-message offsets only after DLQ
publication succeeded. That safety posture was correct, but when the DLQ path itself stayed
unavailable, the same terminal poison message could redeliver indefinitely and block partition
progress until the DLQ dependency recovered.

## Action Taken

Added a configurable shared DLQ publication failure budget:

- `KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS=0` keeps the existing default behavior: no offset commit
  after DLQ failure, allowing Kafka redelivery.
- A positive value tracks failures by `topic`, `group_id`, `partition`, `offset`, and key.
- Before exhaustion, the consumer keeps the current safe no-commit behavior.
- At exhaustion, the consumer emits bounded `kafka.consumer.dlq_failure_budget_exhausted`
  structured log evidence, emits `kafka_consumer_events_total{outcome="dlq_failure_budget_exhausted"}`,
  stops the run loop, and raises `DlqPublicationBudgetExhausted` without committing the terminal
  message offset.
- Successful DLQ publication clears any prior failure count for the message.

The exhaustion path records source-safe metadata only: original topic, partition, offset, DLQ
topic, attempt counts, and processing error type. It does not log payloads or raw exception text.

## Compatibility

Default runtime behavior is preserved because the budget defaults to disabled (`0`). Existing
consumers continue to leave offsets uncommitted on DLQ failure unless operators explicitly configure
a positive budget.

No API route, OpenAPI schema, Kafka topic, event payload, database schema, DLQ payload, consumer
success behavior, or durable DLQ success record changed. The intentional behavior change is opt-in:
configured consumers fail fast instead of continuing unbounded redelivery after repeated DLQ
publication failure for the same terminal message.

## Tests Added

Extended `tests/unit/libs/portfolio-common/test_kafka_consumer.py` with direct run-loop coverage
for:

1. default no-commit behavior tracking the first DLQ failure attempt,
2. positive budget exhaustion failing fast without committing the offset,
3. transient DLQ failure below the budget still allowing redelivery,
4. successful DLQ publication clearing prior failure attempts.

Extended `tests/unit/libs/portfolio-common/test_config.py` with environment parsing coverage for
valid and invalid `KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS` values.

## Validation

Focused behavior proof:

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py -q`
- Result: `68 passed`

Static proof:

- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py`
- Result: passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py`
- Result: `4 files already formatted`

Measured quality proof:

- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s -a`
- Result: new DLQ failure-budget helpers are A-ranked; average complexity remains A.
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_consumer.py -s`
- Result: module maintainability remains `B (14.47)`.

## Documentation And Wiki Decision

Updated the operations runbook, repository context, codebase review ledger, quality scorecard, and
refactor health report because the slice adds an operator-visible runtime setting and shared
consumer failure policy. No repo-local wiki source page changed in this slice.

Wiki publication check:

- `..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed on pre-existing published-wiki drift for `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, and `Outbox-Events.md`; no repo-local wiki
  source page changed in CR-1261.

## Follow-Up

If the platform later requires durable local quarantine while DLQ is unavailable, add a dedicated
durable quarantine store with retention, replay, and access-control semantics. This slice
intentionally uses controlled fail-fast as the bounded fallback because the shared library does not
own a service-specific durable local store.

## Bank-Buyable Control Movement

This slice improves:

1. poison-message containment when DLQ is unavailable,
2. explicit offset-commit behavior for each DLQ failure mode,
3. low-cardinality fleet telemetry for DLQ dependency exhaustion,
4. source-safe operator evidence,
5. reusable shared-consumer resilience policy instead of service-local patches.
