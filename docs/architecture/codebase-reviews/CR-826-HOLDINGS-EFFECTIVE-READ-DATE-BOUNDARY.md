# CR-826 Holdings Effective Read Date Boundary

## Status

Hardened on 2026-06-01.

## Scope

`src/services/query_service/app/services/position_service.py`,
`src/services/query_service/app/services/position_holdings_reads.py`, and
`tests/unit/services/query_service/services/test_position_holdings_reads.py`.

## Finding

`PositionService.get_portfolio_positions(...)` still owned the repository lookup for the default
latest business date and the effective HoldingsAsOf read-date resolution.

That kept request-scope repository lookup policy inside the service method even after the
source-row, fallback valuation, and support-evidence reads moved into `position_holdings_reads.py`.

## Action

Added `effective_holdings_read_as_of_date(...)` to `position_holdings_reads.py`. The helper reads
the latest business date only for booked latest reads, preserves explicit as-of dates, and keeps
projected latest reads unbounded. Routed `PositionService.get_portfolio_positions(...)` through
the helper and added direct tests for default, explicit, and projected read scopes.

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
