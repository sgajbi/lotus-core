# CR-813 Holdings Policy Module Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` and the HoldingsAsOf helper policies in the
query-service holdings read path.

## Finding

After the CR-805 through CR-812 extractions, `position_service.py` still owned both repository
orchestration and a large cluster of HoldingsAsOf transformation helpers. That reduced inline
complexity, but the file still mixed service coordination with merge policy, fallback valuation
scope, valuation mapping, response DTO mapping, weight assignment, held-since evidence, market
price freshness scope, response as-of date resolution, and final response assembly.

Keeping those policies in the service module made the service file broader than its orchestration
responsibility and made future reuse harder.

## Action

Created `position_holdings.py` as the dedicated HoldingsAsOf policy module and moved the extracted
helpers there. `position_service.py` now imports those helpers and keeps the service responsible
for portfolio existence checks, repository reads, and orchestration.

The existing focused helper tests now import from `position_holdings.py`, so the module boundary is
covered directly while preserving service-level behavior.

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
