# CR-788 Index Catalog Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.list_index_catalog(...)` in the market reference-data catalog path.

## Finding

Index catalog orchestration still coordinated index definition repository reads and response
assembly inline in the broad integration service.

That left the integration service as the owner of index catalog workflow policy even though the
index catalog module already owned index definition response mapping.

## Action

Added `resolve_index_catalog_response(...)` to `index_catalog.py`, then routed
`IntegrationService.list_index_catalog(...)` through that helper with the existing reference
repository dependency.

The service still owns dependency wiring. The index catalog module now owns the full catalog
response workflow after dependency injection: index definition read predicates and response
assembly. Focused helper coverage locks repository read arguments, returned records, and
empty-catalog behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

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
