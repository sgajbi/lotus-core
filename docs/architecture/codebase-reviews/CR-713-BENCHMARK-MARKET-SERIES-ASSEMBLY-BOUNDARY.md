# CR-713 Benchmark Market Series Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the query service benchmark/reference
source-data product surface.

## Finding

The benchmark market-series endpoint had a real hot-path contract but kept read-plan policy and
response assembly inline with repository orchestration. Requested-field handling, benchmark-to-target
FX context decisions, page-scoped component evidence, point assembly, quality summary generation, and
runtime metadata all lived inside the service method.

That made it harder to audit which request fields trigger which repository reads and harder to keep
page-scoped evidence semantics stable for large benchmark component universes.

## Action

Added `benchmark_market_series.py` as the focused benchmark market-series policy boundary.

The service now:

1. resolves benchmark currency and page scope,
2. asks the helper for FX read/context policy,
3. executes repository reads sequentially on the request-scoped session,
4. delegates component window resolution, point assembly, page metadata, lineage, quality summary,
   and runtime metadata.

Focused helper coverage locks:

1. identity benchmark-to-target FX context,
2. missing FX-context request handling,
3. FX evidence normalization status,
4. page-scoped response metadata,
5. quality summary and latest-evidence timestamp behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_market_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\benchmark_market_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_market_series.py
python -m ruff format --check src\services\query_service\app\services\benchmark_market_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_market_series.py
git diff --check
```
