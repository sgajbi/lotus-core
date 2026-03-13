# CR-159 Valuation Stale Retry Ceiling Review

## Scope

- Durable valuation job recovery
- Valuation scheduler runtime settings
- Banking-grade terminal failure semantics for stale control work

## Finding

`PortfolioValuationJob` stale recovery still reset `PROCESSING` rows back to
`PENDING` forever. That left the valuation queue inconsistent with the replay
queue after CR-158 and meant repeated worker crashes could cause infinite retry
cycling on a durable control table.

## Fix

- Added configurable `VALUATION_SCHEDULER_MAX_ATTEMPTS` with default `3`
- `ValuationRepository.find_and_reset_stale_jobs(...)` now:
  - resets stale `PROCESSING` rows only while `attempt_count < max_attempts`
  - marks stale rows `FAILED` once `attempt_count >= max_attempts`
  - records a durable failure reason
- `ValuationScheduler` now passes the configured retry ceiling into stale-job
  recovery

## Evidence

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `src/services/valuation_orchestrator_service/app/settings.py`
- `tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`

## Validation

- valuation worker metric + scheduler + DB-backed repository slice:
  - `23 passed`
- `ruff check`:
  - passed

## Follow-up

- Apply the same terminal stale-retry symmetry to the aggregation queue so all
  durable control queues share one failure model.
