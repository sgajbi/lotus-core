# CR-160 Aggregation Stale Retry Ceiling Review

## Scope

- Durable portfolio aggregation job recovery
- Aggregation scheduler runtime settings
- Symmetric terminal failure semantics across durable control queues

## Finding

`PortfolioAggregationJob` stale recovery had not been brought up to the same
durable standard as replay and valuation queues. The queue had no
`attempt_count` or `failure_reason`, stale `PROCESSING` rows reset back to
`PENDING` forever, and the scheduler had no configurable retry ceiling.

## Fix

- Added durable aggregation queue metadata:
  - `attempt_count`
  - `failure_reason`
- Added configurable `AGGREGATION_SCHEDULER_MAX_ATTEMPTS` with default `3`
- `TimeseriesRepository.find_and_reset_stale_jobs(...)` now:
  - resets stale `PROCESSING` rows only while `attempt_count < max_attempts`
  - marks stale rows `FAILED` once `attempt_count >= max_attempts`
  - records a durable failure reason
- `find_and_claim_eligible_jobs(...)` now increments `attempt_count` on claim
- Added Alembic migration so the durable queue model matches the repository
  contract

## Evidence

- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py`
- `src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py`
- `src/services/portfolio_aggregation_service/app/settings.py`
- `alembic/versions/f5e6f7a8b9c0_feat_add_aggregation_retry_metadata.py`
- `tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
- `tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py`
- `tests/integration/services/timeseries_generator_service/test_int_timeseries_repo.py`

## Validation

- focused aggregation repository + scheduler + DB-backed integration slice:
  - `17 passed`
- `ruff check`:
  - passed
- `ruff format --check`:
  - passed
- `migration_contract_check --mode alembic-sql`:
  - passed

## Follow-up

- Surface terminal `FAILED` aggregation jobs in explicit Prometheus telemetry if
  operators need alerting beyond logs and durable queue inspection.
