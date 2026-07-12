# CR-800 Index Price Series Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_index_price_series(...)` in the query-service market reference index
series boundary.

## Finding

Index price series response assembly already lived in `index_price_series.py`, but the broad
integration service still coordinated index price series repository lookup and response assembly
inline.

That kept RFC-062 index series workflow ownership split across the integration service and the
owning index price series module.

## Action

Added `resolve_index_price_series_response(...)` to `index_price_series.py` and routed
`IntegrationService.get_index_price_series(...)` through that resolver with the existing reference
repository dependency.

The service still owns dependency wiring. The index price series module now owns the full response
workflow after dependency injection: index price read predicates, resolved window, point mapping,
lineage, data-quality posture, runtime metadata, and response assembly. Focused helper coverage
locks repository read arguments and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_index_price_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\index_price_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_price_series.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\index_price_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_price_series.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
