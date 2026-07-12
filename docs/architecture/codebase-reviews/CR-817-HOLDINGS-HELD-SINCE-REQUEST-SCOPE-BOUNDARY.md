# CR-817 Holdings Held-Since Request Scope Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` and the HoldingsAsOf held-since support-evidence
request scope.

## Finding

`PositionService.get_portfolio_positions(...)` still shaped the held-since repository request
inline by projecting indexed held-since requests into `(security_id, epoch)` pairs. The method also
duplicated the market-price freshness evidence read across the held-since and no-held-since
branches.

That kept support-evidence request-shaping policy in the service and made the service branch
broader than needed for repository orchestration.

## Action

Added `held_since_security_epoch_pairs(...)` to `position_holdings.py` and routed held-since
repository requests through it. The service now applies held-since evidence when needed and reads
market-price freshness evidence once afterward for the shared HoldingsAsOf data-quality
classification path.

Added focused helper coverage proving the repository request shape drops list indexes and default
dates while preserving ordered `(security_id, epoch)` identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
module-boundary extraction and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_holdings.py tests\unit\services\query_service\services\test_position_service.py
python -m ruff format --check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_holdings.py tests\unit\services\query_service\services\test_position_service.py
git diff --check
```
