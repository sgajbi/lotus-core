# CR-822 Holdings Support Evidence Test Boundary

## Status

Hardened on 2026-06-01.

## Scope

`tests/unit/services/query_service/services/test_position_service.py` and
`tests/unit/services/query_service/services/test_position_holdings.py`.

## Finding

After CR-821 moved holdings response mapping tests into the dedicated holdings test module,
held-since support-evidence, market-price freshness, data-quality classification, and latest
evidence timestamp helper tests still lived in `test_position_service.py`.

Those tests directly exercise `position_holdings.py` helper policy and do not require
`PositionService` orchestration or repository mocks. Keeping them in the service test file
continued to mix reusable HoldingsAsOf supportability policy proof with service-orchestration
coverage.

## Action

Moved the held-since request, held-since application, market-price freshness scope,
data-quality status, and latest evidence timestamp helper tests into `test_position_holdings.py`.
Removed now-unused direct holdings DTO imports from `test_position_service.py`.

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
