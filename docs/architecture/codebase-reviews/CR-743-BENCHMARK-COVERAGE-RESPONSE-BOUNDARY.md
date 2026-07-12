# CR-743 Benchmark Coverage Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_coverage(...)` in the market/reference source-data product path.

## Finding

Benchmark coverage response assembly still built the request fingerprint inline in the broad
integration service before invoking the shared market-reference coverage mapper.

That kept benchmark-specific coverage identity policy coupled to orchestration instead of making
the benchmark coverage response boundary reusable and directly testable.

## Action

Added `benchmark_coverage.py` as the focused benchmark coverage response boundary.

The service now reads benchmark coverage evidence and delegates fingerprinted response assembly.
Focused helper coverage locks benchmark-scoped fingerprinting, source-data runtime metadata,
missing-date sampling, and quality distribution mapping.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_coverage.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_coverage.py
python -m ruff format --check src\services\query_service\app\services\benchmark_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_coverage.py
git diff --check
```
