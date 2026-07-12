# CR-802 Benchmark Return Series Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_return_series(...)` in the query-service market reference
benchmark series boundary.

## Finding

Benchmark return series response assembly already lived in `benchmark_return_series.py`, but the
broad integration service still coordinated benchmark return repository lookup and response
assembly inline.

That kept RFC-062 benchmark return workflow ownership split across the integration service and the
owning benchmark return series module.

## Action

Added `resolve_benchmark_return_series_response(...)` to `benchmark_return_series.py` and routed
`IntegrationService.get_benchmark_return_series(...)` through that resolver with the existing
reference repository dependency.

The service still owns dependency wiring. The benchmark return series module now owns the full
response workflow after dependency injection: benchmark return read predicates, request
fingerprint scope, resolved window, point mapping, lineage, and response assembly. Focused helper
coverage locks repository read arguments and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_return_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_return_series.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\benchmark_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_return_series.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
