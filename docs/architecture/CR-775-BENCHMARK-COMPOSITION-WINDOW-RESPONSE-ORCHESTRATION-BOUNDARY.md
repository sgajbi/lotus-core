# CR-775 Benchmark Composition Window Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_composition_window(...)` in the benchmark composition source-data
path.

## Finding

Benchmark composition orchestration still coordinated definition-window reads, missing-definition
short-circuit behavior, component-window reads, and response assembly inline in the broad
integration service.

That left the integration service as the owner of benchmark composition workflow policy even though
the benchmark composition module already owned definition-context validation, currency drift
rejection, segment resolution, lineage, and source-data runtime metadata.

## Action

Added `resolve_benchmark_composition_window_response(...)` to `benchmark_composition.py`, then routed
`IntegrationService.get_benchmark_composition_window(...)` through that helper with the existing
reference repository dependency.

The service still owns dependency wiring. The benchmark composition module now owns the full
source-data response workflow after dependency injection: definition-window reads, missing-definition
short-circuiting, component-window reads, definition-context validation, and response assembly.
Focused helper coverage locks repository read arguments, read order, and no-component-read behavior
when definitions are unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_composition.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_composition.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_composition.py
python -m ruff format --check src\services\query_service\app\services\benchmark_composition.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_composition.py
git diff --check
```
