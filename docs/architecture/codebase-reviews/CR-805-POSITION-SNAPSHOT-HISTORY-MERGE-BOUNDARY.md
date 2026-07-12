# CR-805 Position Snapshot History Merge Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path mixed repository orchestration, snapshot/history merge policy,
valuation fallback, DTO construction, weight calculation, held-since evidence, and source-product
runtime metadata in one large method.

The snapshot/history merge policy is domain-significant: snapshot rows are authoritative for a
security, while history rows supplement securities missing from the snapshot feed. Keeping that
policy inline made the holdings read path harder to review and test independently.

## Action

Extracted `merge_snapshot_and_history_position_rows(...)` in `position_service.py` and routed
`PositionService.get_portfolio_positions(...)` through it.

The helper now owns the normalized security-key merge rule, history supplement selection, and
snapshot security identity set. Focused coverage locks snapshot authority over duplicate history
rows and inclusion of history-only securities.

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
