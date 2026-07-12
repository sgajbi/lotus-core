# CR-143 Instrument Trigger Repository Ownership Convergence Review

## Scope
- valuation orchestrator replay-trigger repository ownership
- shared valuation repository surface

## Finding
The shared `ValuationRepositoryBase` still carried instrument replay trigger claim/count behavior even though only the valuation orchestrator uses that path. That blurred ownership and let worker-specific trigger behavior appear shared purely because the tests were still anchored under the worker repository tree.

## Fix
- Moved instrument trigger claim/count methods into the real owner:
  - `src/services/valuation_orchestrator_service/app/repositories/valuation_repository.py`
- Removed those methods from the shared base class.
- Moved the DB-backed trigger repository proof under valuation orchestrator ownership.

## Validation
- `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py src/services/valuation_orchestrator_service/app/repositories/valuation_repository.py tests/integration/services/valuation_orchestrator_service/test_replay_trigger_repository.py`
- `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py -q`
- DB-backed replay trigger file updated to the new owner path; local rerun of that integration file remains blocked by the same Docker compose build-layer issue already isolated outside this repository change.

## Status
- Hardened
