# CR-816 Holdings Position List Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` and the HoldingsAsOf position-row assembly policy.

## Finding

`PositionService.get_portfolio_positions(...)` still assembled the public holdings position list
inline after snapshot/history merge and fallback valuation lookup. The inline loop owned
snapshot-vs-history identity, normalized security lookup, valuation fallback selection, and
position DTO creation orchestration even though the individual mapping helpers already lived in
`position_holdings.py`.

Keeping the row loop in the service made the method continue to mix repository coordination with
HoldingsAsOf transformation policy.

## Action

Added `portfolio_position_rows_data(...)` to `position_holdings.py` and routed
`PositionService.get_portfolio_positions(...)` through it. The service now hands off merged rows,
snapshot-authority identity, and fallback valuation evidence to the HoldingsAsOf policy module.

Added focused helper coverage for snapshot-backed valuation mapping, history-backed fallback
valuation mapping, normalized security identity, missing-instrument fallback behavior, and
reprocessing-status propagation.

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
