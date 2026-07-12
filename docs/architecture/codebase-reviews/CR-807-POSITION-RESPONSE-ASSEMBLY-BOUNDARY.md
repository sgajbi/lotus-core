# CR-807 Position Response Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still assembled the public `Position` DTO inline after the
snapshot/history merge and valuation fallback extraction. That kept every holdings response field
mapping inside the orchestration method, including normalized security identity, snapshot versus
history date selection, instrument enrichment, missing-instrument fallback behavior, valuation
attachment, and reprocessing status.

Keeping those mappings inline made the service method harder to review and made the holdings
response vocabulary less directly testable.

## Action

Extracted `position_response_data(...)` in `position_service.py` and routed
`PositionService.get_portfolio_positions(...)` through that helper.

The helper now owns normalized holdings DTO construction for snapshot-backed and history-backed
rows. Focused coverage locks instrument enrichment, snapshot date mapping, history date mapping,
the missing-instrument fallback, valuation attachment, and reprocessing status propagation.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py tests\unit\services\query_service\services\test_position_service.py
python -m ruff format --check src\services\query_service\app\services\position_service.py tests\unit\services\query_service\services\test_position_service.py
git diff --check
```
