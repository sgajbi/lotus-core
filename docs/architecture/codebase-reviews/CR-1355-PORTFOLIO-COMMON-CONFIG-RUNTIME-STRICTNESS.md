# CR-1355 Portfolio Common Config Runtime Strictness

## Scope

Complete the GitHub issue #600 same-pattern runtime-settings pass for shared
`portfolio_common.config`.

## Objective

Stop resilience-critical shared configuration from silently accepting malformed or out-of-range
runtime values in strict or production-like profiles while preserving local compatibility fallback.

## Changes

1. Replaced the local `_env_int(...)` and `_env_bool(...)` fallback logic with
   `portfolio_common.runtime_settings` helpers.
2. Routed Kafka consumer defaults and group override JSON through the shared JSON env helper.
3. Kept local/development fallback behavior for invalid integer, boolean, and JSON settings.
4. Added strict-profile tests for:
   - malformed integer values;
   - malformed boolean values;
   - business-date future-day guardrail values;
   - cashflow cache TTL values;
   - Kafka retry elapsed seconds;
   - malformed Kafka consumer defaults JSON;
   - non-object Kafka consumer group override JSON.

## Behavior And Compatibility

Existing unset defaults, environment variable names, Kafka topic names, consumer override keys,
database schema, event payloads, OpenAPI schemas, route paths, and service topology are unchanged.

Intentional behavior change: strict or non-local deployments now fail fast on invalid shared
business-date, cashflow-cache, Kafka failure-budget, and Kafka consumer override JSON settings.

Local/development profiles still fall back to the existing defaults and log the fallback.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\libs\portfolio-common\test_config.py tests\unit\libs\portfolio-common\test_runtime_settings.py tests\unit\libs\portfolio-common\test_kafka_consumer.py -q`
   - Result: `92 passed`.
2. `python -m ruff check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
   - Result: passed.
3. `python -m ruff format --check src\libs\portfolio-common\portfolio_common\config.py tests\unit\libs\portfolio-common\test_config.py`
   - Result: passed.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger and repo-local engineering context.

No wiki source update is required because this changes invalid-runtime-config handling, not an
operator command, API shape, support workflow, or published feature capability.

No central Lotus skill change is required. The current backend-delivery and issue-loop skills
already require same-pattern fixes, repo context updates, and explicit no-skill-change decisions.
