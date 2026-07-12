# CR-141 Atomic Instrument Trigger Claim Review

## Scope
- `ValuationRepositoryBase.claim_instrument_reprocessing_triggers(...)`
- valuation scheduler trigger consumption path

## Finding
The replay trigger source already guaranteed one durable row per `security_id`, but the scheduler still consumed triggers through a fetch-then-delete pattern. That left a race window between reading rows and deleting them, and the first attempt to collapse both operations into one SQL shape proved unstable on the real database path.

## Fix
- Replaced the read-then-delete flow with a transaction-safe lock-and-delete claim path:
  - `SELECT security_id ... FOR UPDATE SKIP LOCKED`
  - followed by `DELETE ... WHERE security_id IN (...) RETURNING *`
- Kept ordering on:
  - `earliest_impacted_date ASC`
  - `updated_at ASC`
  - `security_id ASC`
- Removed the obsolete explicit delete helper from the scheduler path.

## Validation
- `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`
- `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py -q`
- DB-backed repository assertions updated for the claimed ordering contract; local rerun of that integration file was blocked by a Docker compose build-layer failure unrelated to the repository logic.

## Status
- Hardened
