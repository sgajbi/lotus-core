# CR-1251 Kafka Consumer Metrics

Date: 2026-07-01

## Objective

Fix GitHub issue #567 by making `BaseConsumer` emit standard low-cardinality Kafka consumer
lifecycle and processing metrics by default.

## Change

- Added `kafka_consumer_events_total{service,topic,group_id,outcome,reason}`.
- Added `kafka_consumer_processing_duration_seconds{service,topic,group_id}`.
- Routed `BaseConsumer` success, retryable failure, terminal failure, DLQ success/failure, commit
  failure, poll error, critical loop exit, and shutdown-failure paths through the shared metrics.
- Kept existing service-local injected metrics as optional extensions for persistence consumers.
- Added focused shared consumer tests for success, retryable failure, DLQ success, DLQ failure,
  commit failure, poll error, and shutdown failure metric emission.
- Confirmed production `confluent_kafka.Consumer` construction is centralized in `BaseConsumer`;
  active service consumers inherit the shared class.

## Expected Improvement

Kafka worker incidents now have consistent fleet-level signals across services that inherit
`BaseConsumer`, without requiring each consumer manager to pass a custom metrics dictionary. Labels
are bounded to service, topic, consumer group, outcome, and reason code; raw exception text,
message keys, offsets, correlation IDs, trace IDs, portfolio IDs, and security IDs stay out of
Prometheus labels.

## Tests Added Or Updated

- Extended `tests/unit/libs/portfolio-common/test_kafka_consumer.py` with standard metric
  assertions across the lifecycle/error paths.
- Extended `tests/unit/libs/portfolio-common/test_monitoring.py` with bounded label assertions.

## Validation Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_monitoring.py tests\unit\scripts\test_metric_vocabulary_guard.py -q --tb=short`
  -> 53 passed.
- `python scripts\metric_vocabulary_guard.py` -> passed.
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_consumer.py src\libs\portfolio-common\portfolio_common\monitoring.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_monitoring.py`
  -> passed.
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_consumer.py src\libs\portfolio-common\portfolio_common\monitoring.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_monitoring.py`
  -> passed.
- `make lint` -> passed, including `metric-vocabulary-guard`.
- `make typecheck` -> passed.
- `make quality-wiki-docs-gate` -> passed.
- `python C:\Users\Sandeep\projects\lotus-platform\codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki`
  -> passed.
- `git diff --check` -> passed.
- `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
  -> failed with published-wiki drift on `Operations-Runbook.md` and pre-existing
  `Outbox-Events.md`; wiki publication remains post-merge.
- Stranded-truth reconciliation: `git fetch origin --prune` and
  `git branch -r --no-merged origin/main` found only active Dependabot branches.
  `origin/dependabot/github_actions/github-actions-02325a8da5` touches workflow dependency
  updates and is classified `active`; `origin/dependabot/pip/python-runtime-b808a9fc65` does not
  touch checked durable governance paths for this slice and is classified `active`.

## Downstream Compatibility

No Kafka topic, payload schema, DLQ payload, database schema, consumer commit policy, retry policy,
route path, API response, or service-local custom metric contract changed. Critical loop exceptions
still propagate; the shared consumer now also records the critical-exit metric and executes the
existing shutdown path in `finally`. The new metrics are additive shared operational telemetry.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, observability docs, operations runbook,
repo-local wiki source, repository context, quality scorecard, and refactor health report because
the operator-facing Kafka consumer metric contract changed. Wiki publication remains post-merge.
