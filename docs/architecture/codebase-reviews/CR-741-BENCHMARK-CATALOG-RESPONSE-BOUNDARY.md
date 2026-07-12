# CR-741 Benchmark Catalog Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.list_benchmark_catalog(...)` in the market/reference source-data product path.

## Finding

Benchmark catalog response assembly was still embedded in the broad integration service.
Definition DTO mapping and effective component attachment lived beside repository orchestration.

That kept catalog mapping policy coupled to the service method and made the list endpoint less
reusable than the surrounding reference-data response boundaries.

## Action

Added `benchmark_catalog.py` as the focused benchmark catalog response boundary.

The service now reads benchmark definitions and effective components, then delegates catalog
response assembly. Focused helper coverage locks definition mapping, component attachment, and the
empty-component default when a benchmark has no effective component rows.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

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
