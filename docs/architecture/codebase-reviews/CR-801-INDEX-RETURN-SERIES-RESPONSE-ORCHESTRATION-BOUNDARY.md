# CR-801 Index Return Series Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_index_return_series(...)` in the query-service market reference index
series boundary.

## Finding

Index return series response assembly already lived in `index_return_series.py`, but the broad
integration service still coordinated index return series repository lookup and response assembly
inline.

That kept RFC-062 index return workflow ownership split across the integration service and the
owning index return series module.

## Action

Added `resolve_index_return_series_response(...)` to `index_return_series.py` and routed
`IntegrationService.get_index_return_series(...)` through that resolver with the existing reference
repository dependency.

The service still owns dependency wiring. The index return series module now owns the full response
workflow after dependency injection: index return read predicates, request fingerprint scope,
resolved window, point mapping, lineage, data-quality posture, runtime metadata, and response
assembly. Focused helper coverage locks repository read arguments and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_index_return_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\index_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_return_series.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\index_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_index_return_series.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
