# CR-828 Position History Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`src/services/query_service/app/services/position_service.py`,
`src/services/query_service/app/services/position_history_reads.py`, and
`tests/unit/services/query_service/services/test_position_history_reads.py`.

## Finding

`PositionService.get_position_history(...)` still normalized the requested security identifier,
called the position-history repository, and assembled the response inline.

That left position-history read orchestration in the service method while HoldingsAsOf read
orchestration had already moved into dedicated helper modules.

## Action

Created `position_history_reads.py` with `position_history_response(...)`. The helper owns
security identifier normalization, repository read arguments, and response assembly through the
existing `position_history.py` mapper. Routed `PositionService.get_position_history(...)` through
the helper and added direct coverage for normalized repository read arguments and returned response
scope.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service-boundary cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_history_reads.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
python -m ruff format --check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_history_reads.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
git diff --check
```
