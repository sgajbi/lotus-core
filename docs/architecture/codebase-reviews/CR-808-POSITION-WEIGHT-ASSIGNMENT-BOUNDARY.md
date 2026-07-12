# CR-808 Position Weight Assignment Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still calculated client-facing holdings weights inline after
position DTO assembly. That logic selected each position's market-value base, fell back to cost
basis when market value was unavailable, summed the portfolio base, and assigned either
proportional weights or zero weights when no positive base value existed.

Keeping that policy inline made the orchestration method harder to review and left an important
private-banking response figure without direct helper-level coverage.

## Action

Extracted `position_weight_base_value(...)` and `assign_position_weights(...)` in
`position_service.py`, then routed `PositionService.get_portfolio_positions(...)` through the
weight-assignment helper.

Focused coverage now locks market-value share weighting, cost-basis fallback weighting, and the
all-zero base-value behavior. The previous service-private `_weight_base_value(...)` wrapper was
removed because the reusable top-level helper now owns that policy directly.

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
