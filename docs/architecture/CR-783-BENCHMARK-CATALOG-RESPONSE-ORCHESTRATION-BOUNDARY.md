# CR-783 Benchmark Catalog Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.list_benchmark_catalog(...)` in the benchmark reference-data catalog path.

## Finding

Benchmark catalog orchestration still coordinated benchmark definition reads, benchmark identifier
projection, component reads for the returned definitions, and response assembly inline in the broad
integration service.

That left the integration service as the owner of benchmark catalog workflow policy even though the
benchmark catalog module already owned definition-to-response mapping and component attachment.

## Action

Added `resolve_benchmark_catalog_response(...)` to `benchmark_catalog.py`, then routed
`IntegrationService.list_benchmark_catalog(...)` through that helper with the existing reference
repository dependency.

The service still owns dependency wiring. The benchmark catalog module now owns the full catalog
response workflow after dependency injection: definition read predicates, component read scope, and
response assembly. Focused helper coverage locks repository read arguments, read order, component
scope derivation, and the existing empty-definition component lookup behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_catalog.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_catalog.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_catalog.py
python -m ruff format --check src\services\query_service\app\services\benchmark_catalog.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_catalog.py
git diff --check
```
