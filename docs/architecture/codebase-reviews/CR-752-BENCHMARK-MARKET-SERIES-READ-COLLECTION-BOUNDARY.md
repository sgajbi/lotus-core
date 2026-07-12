# CR-752 Benchmark Market Series Read Collection Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-reference path.

## Finding

Benchmark market-series orchestration still assembled ordered evidence read names, selected optional
read families, and collected async repository results inline after building the evidence plan.

That kept market-reference read-order policy coupled to the broad integration service instead of the
benchmark market-series module that owns request scope, evidence planning, paging, FX context,
normalization, and response assembly.

## Action

Added `benchmark_market_series_evidence_read_names(...)` and
`benchmark_market_series_read_evidence(...)` to `benchmark_market_series.py`, then routed the
integration service through read factories supplied by the repository boundary.

The service still owns repository dependency wiring and arguments, while the benchmark market-series
module now owns selected-family ordering and async evidence-result collection. Focused helper
coverage locks repository read order and proves unplanned families are not invoked.

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
