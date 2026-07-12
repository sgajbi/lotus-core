# CR-809 Position Support Evidence Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still prepared held-since support-evidence requests, assigned
default held-since dates, applied repository-returned held-since dates, and selected market-price
freshness security IDs inline. That mixed client-facing holdings assembly with supportability
evidence policy and data-quality inputs.

Keeping that logic inline made the service method harder to review and kept operational evidence
behavior less directly testable.

## Action

Extracted `position_held_since_requests(...)`, `apply_held_since_dates(...)`,
`position_requires_market_price_freshness(...)`, and `market_price_freshness_security_ids(...)` in
`position_service.py`, then routed `PositionService.get_portfolio_positions(...)` and holdings
data-quality classification through those helpers.

Focused coverage now locks missing-epoch default held-since behavior, normalized epoch requests,
held-since map fallback behavior, and market-price freshness filtering for cash and unpriced rows.

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
