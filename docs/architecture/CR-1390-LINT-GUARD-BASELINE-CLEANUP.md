# CR-1390 Lint Guard Baseline Cleanup

## Objective

Restore the repo-native `make lint` baseline after the #602 matrix slice surfaced two existing
guard failures.

## Changes

1. Updated the ingestion gateway rate-limit policy guard to discover ingestion `POST` route
   templates from FastAPI router decorators instead of only `endpoint="..."` keyword literals.
2. Kept `/ingest/uploads/preview` outside the global write-commit gateway policy because it is
   local parse-rate protection, not a committed write endpoint.
3. Removed direct `os.getenv` reads from shared Kafka consumer and producer policy modules by using
   `portfolio_common.runtime_settings` helpers consistently.

## Impact

No runtime behavior, API contract, database schema, event payload, Kafka topic, rate-limit budget,
or deployment topology changed. This is a guard and configuration-access cleanup that keeps the
aggregate lint lane aligned with the current code structure.

## Validation

```powershell
python -m pytest tests/unit/scripts/test_ingestion_gateway_rate_limit_policy_guard.py -q
python scripts/ingestion_gateway_rate_limit_policy_guard.py
python scripts/config_access_guard.py
python -m pytest tests/unit/libs/portfolio-common/test_config.py tests/unit/libs/portfolio-common/test_kafka_utils.py tests/unit/libs/portfolio-common/test_kafka_consumer.py -q
python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer_execution.py src/libs/portfolio-common/portfolio_common/kafka_producer_policy.py scripts/ingestion_gateway_rate_limit_policy_guard.py tests/unit/scripts/test_ingestion_gateway_rate_limit_policy_guard.py --ignore E501,I001
python -m ruff format --check src/libs/portfolio-common/portfolio_common/kafka_consumer_execution.py src/libs/portfolio-common/portfolio_common/kafka_producer_policy.py scripts/ingestion_gateway_rate_limit_policy_guard.py tests/unit/scripts/test_ingestion_gateway_rate_limit_policy_guard.py
make lint
```

## Documentation Decision

No repository context or wiki source update is required. Existing repo context already directs
runtime configuration through `portfolio_common.runtime_settings`; this slice makes the code and
guards comply with that current truth.
