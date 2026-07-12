# CR-818 Holdings Effective As-Of Scope Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` and the HoldingsAsOf effective as-of date request
scope.

## Finding

`PositionService.get_portfolio_positions(...)` still owned the policy deciding whether a request
should use the latest booked business date, an explicit requested as-of date, current-date fallback
when no business date exists, or unbounded latest reads when projected rows are included.

That policy is part of the HoldingsAsOf read-scope contract, while the service should only
coordinate portfolio validation and repository reads.

## Action

Added `should_use_default_holdings_as_of_date(...)` and `effective_holdings_as_of_date(...)` to
`position_holdings.py`, then routed the service through those helpers. The repository read
sequence is unchanged: the service still fetches latest business date only when the helper
identifies the default booked-latest scope.

Added focused helper coverage for explicit as-of date precedence, latest-business-date scope,
current-date fallback, and projected unbounded latest reads.

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
