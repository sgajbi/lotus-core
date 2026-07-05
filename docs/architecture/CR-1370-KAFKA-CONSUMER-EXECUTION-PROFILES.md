# CR-1370 Kafka Consumer Execution Profiles

## Objective

Fix GitHub issue #575 by making Kafka consumer poll cadence, in-flight limits, ordering policy,
shutdown drain budget, and overload behavior explicit shared runtime policy.

## Changes

- Added `KafkaConsumerExecutionProfile` in `portfolio_common.kafka_consumer_execution`.
- Added default and per-group profile loading through:
  - `LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON`
  - `LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON`
- Routed `BaseConsumer` polling through the profile-owned `poll_timeout_seconds`.
- Added bounded concurrent processing for explicitly configured consumers while preserving one
  active message per partition.
- Paused polling when ordered same-partition work is queued, treating it as backlog pressure.
- Added standard metrics for in-flight work, idle polls, and backlog pressure.

## Expected Improvement

- Keeps existing serial behavior by default.
- Lets safe workers opt into cross-partition concurrency without service-local loop rewrites.
- Makes application-level worker capacity visible and strict-validation aware.
- Prevents hidden hard-coded poll cadence from drifting across consumer implementations.

## Correctness And Ordering

- Default `max_in_flight_messages=1` preserves historical serial processing.
- Concurrent profiles process at most one message per partition at a time.
- Offsets are still committed only from `_process_polled_message(...)` after processing or DLQ
  publication succeeds.
- Retryable failures and DLQ publication failures still leave offsets uncommitted.
- `per_key_concurrency` currently must remain `1`; raising it requires a separate ordered commit
  manager design.

## Tests Added

- Config tests for default serial profile, group override merging, local fallback, and strict
  rejection.
- Consumer tests for configured poll timeout.
- Consumer tests proving concurrent cross-partition processing does not commit before completion.
- Consumer tests proving same-partition messages do not process out of order.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_config.py -q
```

Final lint, architecture, docs, and diff checks are recorded in the issue comment before commit.

## Downstream Compatibility Impact

No API route, DTO schema, OpenAPI schema, database schema, Kafka topic, event payload, persistence
model, or runtime topology changed. Existing consumers retain serial processing unless an operator
explicitly configures a group execution profile.

## Same-Pattern Scan

All current `BaseConsumer` subclasses inherit the shared profile behavior. No service-local consumer
poll loops were added. Future cost, position, cashflow, valuation, reconciliation, persistence, and
timeseries workers should use the shared profile instead of adding local poll timeout or concurrency
settings.

## Docs, Context, And Skill Decision

- Operations runbook updated with execution-profile settings and metrics.
- Repository context updated with the shared consumer execution-profile rule.
- No platform skill update is required for this slice; the recurring repo-local failure pattern is
  captured in shared code, tests, the review ledger, and repo context.

## Remaining Hotspots

The shared profile intentionally supports only one active message per partition. Higher
per-key/per-partition concurrency requires an ordered partition commit manager and should not be
introduced as a local worker optimization.
