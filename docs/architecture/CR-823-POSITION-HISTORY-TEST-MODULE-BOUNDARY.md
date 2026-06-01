# CR-823 Position History Test Module Boundary

## Status

Hardened on 2026-06-01.

## Scope

`tests/unit/services/query_service/services/test_position_service.py` and
`tests/unit/services/query_service/services/test_position_history.py`.

## Finding

After the HoldingsAsOf helper-policy tests were moved out of `test_position_service.py`, direct
position-history response helper tests still remained at the top of the service test module.

Those tests exercise `position_history.py` helper behavior directly and do not need
`PositionService` orchestration or repository mocks. Keeping them in the service test module kept
response assembly proof mixed with service behavior proof.

## Action

Created `test_position_history.py` for direct `position_history.py` helper coverage and moved the
position-history record mapping and portfolio position-history response assembly tests into that
module. Removed the direct `position_history.py` helper imports from `test_position_service.py`.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal test-ownership cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_history.py tests\unit\services\query_service\services\test_position_holdings.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_history.py tests\unit\services\query_service\services\test_position_holdings.py
python -m ruff format --check tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_history.py tests\unit\services\query_service\services\test_position_holdings.py
git diff --check
```
