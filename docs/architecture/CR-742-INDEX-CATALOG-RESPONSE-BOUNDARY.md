# CR-742 Index Catalog Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.list_index_catalog(...)` in the market/reference source-data product path.

## Finding

Index catalog response assembly was still embedded in the broad integration service. The service
method read effective index definitions and immediately mapped repository rows into response DTOs
inline.

That kept index catalog mapping coupled to orchestration even though adjacent market-reference
series and taxonomy response boundaries were already helper-owned.

## Action

Added `index_catalog.py` as the focused index catalog response boundary.

The service now reads index definitions and delegates response assembly. Focused helper coverage
locks index definition mapping and empty-catalog behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_index_catalog.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\index_catalog.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_catalog.py
python -m ruff format --check src\services\query_service\app\services\index_catalog.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_catalog.py
git diff --check
```
