# CR-145 Scheduler Backfill Correlation Scope Review

## Scope
- valuation scheduler backfill job lineage
- durable valuation job auditability

## Finding
Scheduler-created backfill jobs were stamped with a date-only correlation id (`SCHEDULER_BACKFILL_<date>`). That is too weak for banking-grade lineage because multiple portfolios, securities, and epochs on the same date collapse onto the same correlation pattern.

## Fix
- Added a scope-stable scheduler correlation builder that includes:
  - `portfolio_id`
  - `security_id`
  - `epoch`
  - `valuation_date`
- Backfill jobs now carry correlation ids of the form:
  - `SCHEDULER_BACKFILL:<portfolio_id>:<security_id>:<epoch>:<valuation_date>`

## Validation
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
- `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py -q`

## Status
- Hardened
