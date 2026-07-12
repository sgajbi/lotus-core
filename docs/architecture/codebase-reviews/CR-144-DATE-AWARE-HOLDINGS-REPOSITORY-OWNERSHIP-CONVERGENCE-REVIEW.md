# CR-144 Date-Aware Holdings Repository Ownership Convergence Review

## Scope
- valuation orchestrator replay-worker holdings lookup
- shared valuation repository surface

## Finding
`find_portfolios_holding_security_on_date(...)` is only used by the replay worker in `valuation_orchestrator_service`, but it still lived on the shared `ValuationRepositoryBase`. That kept worker-only fanout logic in a shared class purely because the test file had historically been under the worker-local repository area.

## Fix
- Moved `find_portfolios_holding_security_on_date(...)` into the valuation orchestrator repository.
- Removed the worker-only method from the shared base class.
- Kept the existing DB-backed holdings proofs under the orchestrator-owned replay trigger repository test area.

## Validation
- `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py src/services/valuation_orchestrator_service/app/repositories/valuation_repository.py tests/integration/services/valuation_orchestrator_service/test_replay_trigger_repository.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
- `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py -q`

## Status
- Hardened
