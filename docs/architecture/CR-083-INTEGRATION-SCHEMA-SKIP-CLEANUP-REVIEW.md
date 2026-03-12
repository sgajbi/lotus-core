# CR-083 Integration Schema Skip Cleanup Review

## Scope
- `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py`
- `tests/integration/services/persistence_service/repositories/test_repositories.py`

## Finding
Three integration tests were still guarded by `pytest.skip(...)` when expected schema objects were absent:

- `position_lot_state`
- `accrued_income_offset_state`
- `transactions.settlement_cash_account_id`
- `transactions.component_type`

These are no longer optional slices. They are part of the active schema and should be enforced as real integration contracts. Leaving them as skips silently weakened coverage and could hide migration regressions.

## Change
Replaced the schema-guard skips with explicit assertions:

- table existence is now required for the lot/offset repository test
- required transaction metadata columns are now asserted for the persistence tests

The tests now fail loudly if the active test schema drifts below the supported baseline.

## Why this is the right fix
- the project is not live and does not need legacy fallback behavior
- schema drift in active integration tests should be visible immediately
- the integration tier is now a stronger contract gate instead of a best-effort compatibility layer

## Residual follow-up
- If future schema evolution intentionally makes a surface optional, express that via test fixture/profile design, not ad hoc `pytest.skip(...)` inside the assertions.

## Evidence
- `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py`
- `tests/integration/services/persistence_service/repositories/test_repositories.py`
