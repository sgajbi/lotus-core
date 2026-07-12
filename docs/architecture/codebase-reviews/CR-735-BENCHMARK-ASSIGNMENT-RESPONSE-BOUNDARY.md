# CR-735 Benchmark Assignment Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_benchmark_assignment(...)` in the benchmark/reference source-data
product path.

## Finding

Benchmark assignment response assembly was still embedded in the broad integration service.
Assignment DTO mapping, assignment version normalization, complete data-quality posture, latest
evidence timestamp selection, and source-data runtime metadata lived beside the repository lookup.

That made the benchmark assignment source-data product less auditable than the surrounding
extracted response boundaries and kept reference-data mapping policy coupled to orchestration.

## Action

Added `benchmark_assignment.py` as the focused benchmark assignment response boundary.

The service now resolves the effective assignment row and delegates response assembly. Focused
helper coverage locks assignment field mapping, integer version normalization, complete
data-quality status, and latest evidence timestamp selection.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_assignment.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_assignment.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_assignment.py
python -m ruff format --check src\services\query_service\app\services\benchmark_assignment.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_assignment.py
git diff --check
```
