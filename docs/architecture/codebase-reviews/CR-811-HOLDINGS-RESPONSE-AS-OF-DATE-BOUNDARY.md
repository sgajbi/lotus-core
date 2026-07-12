# CR-811 Holdings Response As-Of Date Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still resolved the response-level `as_of_date` inline. That rule
is user-visible and data-quality significant: an explicit or effective as-of date should win,
otherwise the response should use the latest assembled position date, and empty holdings should
fall back to the current date.

Keeping that rule inline made response metadata behavior harder to review and test deterministically.

## Action

Extracted `holdings_response_as_of_date(...)` in `position_service.py`, then routed
`PositionService.get_portfolio_positions(...)` through that helper.

Focused coverage now locks explicit effective date precedence, latest-position fallback behavior,
and empty-position current-date fallback behavior with deterministic test dates.

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
