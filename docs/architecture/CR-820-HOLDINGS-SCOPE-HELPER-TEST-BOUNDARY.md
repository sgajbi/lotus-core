# CR-820 Holdings Scope Helper Test Boundary

## Status

Hardened on 2026-06-01.

## Scope

`tests/unit/services/query_service/services/test_position_service.py` and
`tests/unit/services/query_service/services/test_position_holdings.py`.

## Finding

After CR-819 created a dedicated HoldingsAsOf helper test module, several pure helper tests still
remained in `test_position_service.py`: snapshot/history merge policy, fallback valuation scope,
and holdings response as-of date resolution. Those tests exercise `position_holdings.py` directly
and do not require a `PositionService` instance or repository mock.

Keeping them in the service test file continued to blur service-orchestration coverage with
HoldingsAsOf helper-policy coverage.

## Action

Moved the snapshot/history merge, fallback valuation scope, and holdings response as-of date helper
tests into `test_position_holdings.py`. `test_position_service.py` now carries less direct helper
coverage and remains more focused on service orchestration.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal test-ownership cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings.py
python -m ruff format --check tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings.py
git diff --check
```
