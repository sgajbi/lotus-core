# CR-739 Benchmark Return Series Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_return_series(...)` in the market/reference source-data product
path.

## Finding

Benchmark return series response assembly was still embedded in the broad integration service.
Deterministic request fingerprinting, resolved-window mapping, benchmark return point DTO mapping,
and lineage lived beside the repository read.

That kept benchmark return mapping policy coupled to orchestration and inconsistent with the
extracted index price, index return, and risk-free series boundaries.

## Action

Added `benchmark_return_series.py` as the focused benchmark return series response boundary.

The service now reads benchmark return rows and delegates response assembly. Focused helper
coverage locks fingerprint generation, resolved-window mapping, point mapping, and lineage.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_return_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_return_series.py
python -m ruff format --check src\services\query_service\app\services\benchmark_return_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_return_series.py
git diff --check
```
