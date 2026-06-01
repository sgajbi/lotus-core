# CR-824 Holdings Repository Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`src/services/query_service/app/services/position_service.py`,
`src/services/query_service/app/services/position_holdings_reads.py`, and
`tests/unit/services/query_service/services/test_position_holdings_reads.py`.

## Finding

`PositionService.get_portfolio_positions(...)` still selected effective-date versus unbounded
latest repository methods inline for snapshot rows, history rows, and fallback valuation reads.

That kept HoldingsAsOf read-scope branching mixed with service orchestration, making the service
method harder to scan and leaving the repository method-selection policy without direct helper
coverage.

## Action

Created `position_holdings_reads.py` with dedicated helpers for HoldingsAsOf repository reads:

1. `holdings_position_source_rows(...)` selects effective as-of or unbounded latest snapshot and
   history row reads.
2. `fallback_holdings_valuation_map(...)` selects whether fallback valuation continuity is needed
   and reads the effective as-of or unbounded latest valuation map.

Routed `PositionService.get_portfolio_positions(...)` through those helpers and added direct tests
for effective-date, unbounded latest, no-fetch, and fallback valuation read scopes.

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
