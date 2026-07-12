# CR-814 Position History Response Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_position_history(...)` and the query-service position-history response
assembly path.

## Finding

After the HoldingsAsOf policy module extraction, `PositionService.get_position_history(...)` still
assembled `PositionHistoryRecord` and `PortfolioPositionHistoryResponse` DTOs inline. That kept
response mapping policy inside the service orchestration method even though the service should own
portfolio existence checks, security identifier normalization, repository reads, and response
handoff.

## Action

Created `position_history.py` as the dedicated position-history response policy module. The module
now owns `position_history_record_data(...)` and `portfolio_position_history_response_data(...)`.
`PositionService.get_position_history(...)` routes repository results through that helper while
preserving portfolio validation, normalized security identity, repository read arguments, and the
public response shape.

Added focused helper coverage for field mapping, `valuation=None` behavior, response scope
preservation, and reprocessing-status propagation.

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
python -m ruff check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_history.py tests\unit\services\query_service\services\test_position_service.py
python -m ruff format --check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_history.py tests\unit\services\query_service\services\test_position_service.py
git diff --check
```
