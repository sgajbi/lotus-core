# CR-806 Position Valuation Fallback Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still embedded valuation construction after the snapshot/history
merge extraction. That logic had three domain-significant branches: snapshot valuation fields,
latest snapshot valuation fallback for history-only rows, and cost-basis continuity while
valuation backfill catches up.

Keeping those branches inline made the holdings method harder to review and made valuation
continuity behavior less directly testable.

## Action

Extracted `position_valuation_data(...)` in `position_service.py` and routed
`PositionService.get_portfolio_positions(...)` through that helper.

The helper now owns snapshot valuation mapping, latest snapshot fallback mapping, and cost-basis
continuity fallback. Focused coverage locks all three branches.

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
