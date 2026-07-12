# CR-1366 Shared Retry Policy Profiles

## Objective

Fix GitHub issue #574 by replacing fixed retry waits in Kafka admin/startup checks and DB-backed
consumers with shared bounded retry profiles that use exponential jitter, explicit retry taxonomy,
max attempts, max elapsed budgets, and source-safe observability.

## Changes

- Added `portfolio_common.retry_policy`.
- Added shared retry profiles:
  - `kafka_admin_startup`
  - `consumer_db_short`
  - `consumer_db_standard`
  - `consumer_db_extended`
- Added retry telemetry metric `retry_policy_events_total` with bounded labels `profile`,
  `outcome`, and `reason`.
- Migrated the named fixed-wait call sites:
  - `portfolio_common.kafka_admin.ensure_topics_exist`
  - `ValuationReadinessConsumer.process_message`
  - `PriceEventConsumer.process_message`
  - `CashflowCalculatorConsumer._process_message_with_retry`
  - `TransactionEventConsumer.process_message`
  - `ReconciliationRequestedConsumer.process_message`
- Updated repo context and the operations runbook.

## Expected Improvement

- Reduces synchronized retry waves during Kafka or database disturbances.
- Makes retryable exception classes explicit at each call site.
- Adds max elapsed budgets where decorators previously only had attempt counts.
- Gives operators a consistent retry-attempt metric and structured log event.
- Reduces design-time duplication by replacing repeated tenacity policy assembly.

## Tests Added

- Shared retry helper uses `wait_random_exponential` with configured bounded jitter.
- Retryable exceptions retry until the attempt budget is exhausted.
- Non-retryable exceptions are not retried.
- Retryable exceptions can succeed after a retry.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_retry_policy.py tests\unit\libs\portfolio-common\test_kafka_admin.py -q
python -m pytest tests\unit\libs\portfolio-common\test_retry_policy.py tests\unit\libs\portfolio-common\test_kafka_admin.py tests\unit\libs\portfolio-common\test_kafka_utils.py tests\unit\libs\portfolio-common\test_event_publisher.py -q
python -m pytest tests\unit\services\valuation_orchestrator_service\consumers\test_valuation_readiness_consumer.py tests\unit\services\valuation_orchestrator_service\consumers\test_price_event_consumer.py -q
python -m pytest tests\unit\services\financial_reconciliation_service\test_reconciliation_requested_consumer.py tests\unit\services\calculators\position_calculator\consumers\test_position_calculator_consumer.py -q
python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py -q
python -m ruff check <changed retry-policy files>
python -m ruff format --check <changed retry-policy files>
make metric-vocabulary-guard
```

Final slice gates are recorded in the commit and issue comment.

## Downstream Compatibility Impact

No API route, DTO, OpenAPI schema, database schema, Kafka topic, Kafka payload, or consumer group
changed.

Intentional behavior change: migrated decorators now retry only explicitly listed transient
exceptions. Unexpected exceptions no longer get retried by tenacity before reaching the existing
consumer error handlers. This aligns retry behavior with the documented retry taxonomy and avoids
retrying validation, configuration, and programming errors.

## Docs, Context, And Skill Decision

- Repo context updated with the shared retry-policy rule.
- Operations runbook updated with profile budgets and retry metric guidance.
- No wiki source update is required because no separate wiki operator workflow changed.
- No platform skill update is required in this slice; the repo-local context is the correct place
  for the concrete `lotus-core` retry profile names and budgets.

## Remaining Hotspots

Other retry loops outside the issue evidence remain future migration scope. New tenacity usage in
`lotus-core` should use `portfolio_common.retry_policy` unless an explicit domain-specific policy is
documented and tested.
