# CR-797 Benchmark Coverage Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_coverage(...)` in the query-service market reference coverage
boundary.

## Finding

Benchmark coverage response assembly already lived in `benchmark_coverage.py`, but the broad
integration service still coordinated the benchmark coverage repository read and response assembly
inline.

That kept market-reference coverage workflow ownership split across the integration service and
the owning benchmark coverage module, while the adjacent risk-free coverage path already used an
owned resolver boundary.

## Action

Added `resolve_benchmark_coverage_response(...)` to `benchmark_coverage.py` and routed
`IntegrationService.get_benchmark_coverage(...)` through that resolver with the existing reference
repository dependency.

The service still owns dependency wiring. The benchmark coverage module now owns the full response
workflow after dependency injection: benchmark coverage read predicates, response fingerprint
scope, and market-reference coverage response assembly. Focused helper coverage locks repository
read arguments and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_coverage.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_coverage.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\benchmark_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_coverage.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
