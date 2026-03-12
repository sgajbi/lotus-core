## CR-124 Date-Aware Reset Watermarks Fanout Review

Status: Hardened

Scope:
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`

Problem:
- `RESET_WATERMARKS` fanout was targeting every portfolio with a `PositionState` row for a security.
- That is broader than the business impact.
- A back-dated price correction should only reset portfolios that actually held the security on the impacted date.

Fix:
- Switched the worker fanout source from `find_portfolios_for_security(...)` to
  `find_portfolios_holding_security_on_date(security_id, earliest_impacted_date)`.
- Added DB-backed proof that:
  - a portfolio holding the security on the impacted date is included
  - a portfolio closed before the impacted date is excluded
  - a portfolio that opens after the impacted date is excluded

Why this matters:
- prevents unnecessary replay pressure
- narrows watermark resets to real business impact
- reduces scheduler churn and replay fanout noise

Evidence:
- unit worker slice: passed
- DB-backed repository slice: passed
