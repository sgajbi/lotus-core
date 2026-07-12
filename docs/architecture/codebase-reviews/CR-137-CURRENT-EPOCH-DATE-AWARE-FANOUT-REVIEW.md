# CR-137 Current-Epoch Date-Aware Fanout Review

## Scope
- `portfolio_common.valuation_repository_base.ValuationRepositoryBase.find_portfolios_holding_security_on_date`
- DB-backed repository proofs for worker-facing portfolio fanout

## Finding
The worker-facing fanout query selected the latest `PositionHistory` row on or before the impacted date, but it did not fence that history against the live `PositionState.epoch`.

That meant a later row from a stale historical epoch could still pull a portfolio into replay even when the current epoch had already reset or reopened independently.

## Fix
- Join `PositionHistory` to `PositionState` on `(portfolio_id, security_id, epoch)`.
- Keep the latest-history-on-or-before-date semantics, but only within the current epoch.
- Strengthen DB-backed proofs so all worker-facing fanout tests seed explicit live `PositionState` rows.

## Evidence
- Repository change:
  - `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- DB-backed tests:
  - `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`

## Validation
- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`

## Status
- Hardened
