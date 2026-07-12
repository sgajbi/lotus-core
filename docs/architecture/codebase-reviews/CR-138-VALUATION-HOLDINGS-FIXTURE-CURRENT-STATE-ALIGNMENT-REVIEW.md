# CR-138 Valuation Holdings Fixture Current-State Alignment Review

## Scope
- holdings lookup proofs in unit and integration valuation repository suites

## Finding
Older holdings fixtures modeled business state only in `PositionHistory` and did not seed the live `PositionState` control row.

Once the repository was correctly fenced by current epoch, those proofs became stale and started failing, not because the repository was wrong, but because the tests were still asserting against a pre-fence world.

## Fix
- Seed explicit live `PositionState` rows in the holdings fixtures used by:
  - `tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py`
  - `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`
- Keep the business expectation unchanged: only portfolios with a positive latest history row in the current epoch on or before the impacted date should be returned.

## Validation
- `python -m pytest tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py -q`
- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py -q`
- `python -m ruff check tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`

## Status
- Hardened
