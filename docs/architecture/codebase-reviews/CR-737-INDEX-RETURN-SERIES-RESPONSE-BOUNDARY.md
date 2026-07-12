# CR-737 Index Return Series Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_index_return_series(...)` in the market/reference source-data product path.

## Finding

Index return series response assembly was still embedded in the broad integration service.
Deterministic request fingerprinting, resolved-window mapping, return point DTO mapping, lineage,
market-reference data-quality classification, latest evidence timestamp selection, and runtime
metadata lived beside the repository read.

That made the index return source-data product less auditable and kept market-reference mapping
policy coupled to orchestration.

## Action

Added `index_return_series.py` as the focused index return series response boundary.

The service now reads index return rows and delegates response assembly. Focused helper coverage
locks fingerprint generation, resolved-window mapping, point mapping, lineage, complete
data-quality classification, and latest evidence timestamp selection.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_index_return_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\index_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_return_series.py
python -m ruff format --check src\services\query_service\app\services\index_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_return_series.py
git diff --check
```
