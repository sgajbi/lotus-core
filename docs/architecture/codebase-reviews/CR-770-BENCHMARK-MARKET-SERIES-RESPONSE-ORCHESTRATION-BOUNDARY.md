# CR-770 Benchmark Market Series Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-series source-data path.

## Finding

Benchmark market-series orchestration still coordinated benchmark definition resolution, request
scope binding, component-index paging, FX context policy, evidence-family planning, evidence reads,
page-token creation, and response assembly inline in the broad integration service.

That made the service method a market-series workflow owner instead of a thin application-service
entry point delegating to the benchmark market-series boundary.

## Action

Added `resolve_benchmark_market_series_response(...)` to `benchmark_market_series.py`, then routed
`IntegrationService.get_benchmark_market_series(...)` through that helper with the existing
repository and page-token codec dependencies.

The service still owns dependency injection and token codec implementation. The benchmark
market-series module now owns the full source-data response workflow after dependency injection:
definition resolution, request-scope validation, page-id resolution, evidence planning, repository
read orchestration, next-page token creation, and response assembly. Focused helper coverage locks
repository read order, page limit policy, encoded token payload shape, and FX normalization outcome.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

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
