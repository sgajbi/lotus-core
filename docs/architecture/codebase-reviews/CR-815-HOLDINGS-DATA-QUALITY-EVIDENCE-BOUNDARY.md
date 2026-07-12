# CR-815 Holdings Data Quality Evidence Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` and the HoldingsAsOf runtime data-quality and
evidence timestamp policy.

## Finding

After the HoldingsAsOf helper module extraction, `position_service.py` still owned two
service-private policy functions: HoldingsAsOf data-quality classification and latest evidence
timestamp selection. Those functions were business/runtime policy, not repository orchestration.
Keeping them inside `PositionService` meant the service still mixed read coordination with
source-data product supportability semantics.

## Action

Moved HoldingsAsOf data-quality classification into `holdings_data_quality_status(...)` and latest
timestamp selection into `latest_holdings_evidence_timestamp(...)` in `position_holdings.py`.
`PositionService.get_portfolio_positions(...)` now routes response metadata through those policy
helpers while retaining portfolio validation, default-date handling, repository reads, and
support-evidence lookup orchestration.

Added focused helper coverage for missing reprocessing-state posture, history-supplement partial
classification, and latest row/state evidence timestamp selection.

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
