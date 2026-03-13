# CR-158 Stale Reprocessing Retry Ceiling and Model Drift Review

## Scope

- Durable `RESET_WATERMARKS` replay job recovery
- `ReprocessingWorker` runtime settings
- SQLAlchemy model alignment with replay ordering migration

## Finding

Two real issues remained on the durable replay queue path:

1. Stale `PROCESSING` replay jobs could bounce between `PROCESSING` and `PENDING`
   forever after repeated worker crashes. That is not acceptable for a durable,
   banking-grade control queue.
2. The SQLAlchemy model still declared the old invalid PostgreSQL index
   expression using `::date` even though the migration had already been corrected
   to use the raw ISO date text path. That left model-level drift on an active
   replay table.

## Fix

- Added configurable `REPROCESSING_WORKER_MAX_ATTEMPTS` with default `3`
- `ReprocessingJobRepository.find_and_reset_stale_jobs(...)` now:
  - resets stale `PROCESSING` rows back to `PENDING` only while
    `attempt_count < max_attempts`
  - marks stale rows `FAILED` once `attempt_count >= max_attempts`
  - records a durable failure reason
- `ReprocessingWorker` now passes the configured retry ceiling into stale-job
  recovery
- Aligned `ReprocessingJob` model metadata to the real replay-ordering index
  expression (`payload->>'earliest_impacted_date'`) so model and migration agree

## Evidence

- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
- `src/services/valuation_orchestrator_service/app/settings.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`

## Validation

- repository + worker unit slice:
  - `20 passed`
- `ruff check`:
  - passed
- `migration_contract_check --mode alembic-sql`:
  - passed

## Follow-up

- If operators need direct alerting on replay jobs hitting the terminal retry
  ceiling, add a dedicated metric rather than relying only on logs and durable
  `FAILED` state.
