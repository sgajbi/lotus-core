# CR-812 Holdings Response Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still assembled the final `PortfolioPositionsResponse` inline,
including source-data-product runtime metadata. That kept HoldingsAsOf response construction tied
to service orchestration instead of a named response boundary.

Keeping this assembly inline made product identity, generated runtime metadata, data-quality
status, evidence timestamp, and positions payload behavior less directly testable.

## Action

Extracted `portfolio_positions_response_data(...)` in `position_service.py`, then routed
`PositionService.get_portfolio_positions(...)` through that helper.

Focused coverage now locks HoldingsAsOf product identity, runtime as-of date, data-quality status,
latest evidence timestamp, restatement posture, reconciliation posture, generated timestamp, and
payload preservation.

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
