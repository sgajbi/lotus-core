# CR-825 Holdings Support Evidence Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`src/services/query_service/app/services/position_service.py`,
`src/services/query_service/app/services/position_holdings_reads.py`, and
`tests/unit/services/query_service/services/test_position_holdings_reads.py`.

## Finding

After CR-824 extracted HoldingsAsOf source-row and fallback valuation reads,
`PositionService.get_portfolio_positions(...)` still coordinated support-evidence reads inline:
held-since repository lookup, held-since application, market-price freshness security selection,
and latest market-price date lookup.

That kept support-evidence read/apply policy mixed into the service method and left the sequential
held-since-then-market-price behavior without direct helper-level proof.

## Action

Added `holdings_support_evidence(...)` to `position_holdings_reads.py`. The helper applies
held-since evidence when requests exist, then reads latest market-price dates for non-cash priced
holdings using the response as-of date. Routed `PositionService.get_portfolio_positions(...)`
through the helper and added direct tests for:

1. held-since evidence application before market-price date reads,
2. skipping held-since repository reads when no held-since requests exist,
3. market-price freshness security scope for priced non-cash positions.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service-boundary cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_holdings_reads.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
python -m ruff format --check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_holdings_reads.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
git diff --check
```
