# CR-736 Index Price Series Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_index_price_series(...)` in the market/reference source-data product path.

## Finding

Index price series response assembly was still embedded in the broad integration service. Resolved
window mapping, point DTO mapping, lineage, market-reference data-quality classification, latest
evidence timestamp selection, and runtime metadata lived beside the repository read.

That made the index price source-data product less auditable and kept market-reference mapping
policy coupled to orchestration.

## Action

Added `index_price_series.py` as the focused index price series response boundary.

The service now reads index price rows and delegates response assembly. Focused helper coverage
locks resolved-window mapping, point mapping, lineage, complete data-quality classification, and
latest evidence timestamp selection.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_index_price_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\index_price_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_price_series.py
python -m ruff format --check src\services\query_service\app\services\index_price_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_price_series.py
git diff --check
```
