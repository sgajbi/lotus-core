# CR-751 Benchmark Market Series Evidence Plan Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-reference path.

## Finding

Benchmark market-series orchestration still interpreted requested series fields inline when
deciding which evidence families to read: index prices, index returns, benchmark returns, and
benchmark-to-target FX rates.

That kept market-reference evidence selection policy coupled to the broad integration service
instead of the benchmark market-series module that already owns request scope, FX context, paging,
normalization, and response assembly.

## Action

Added `BenchmarkMarketSeriesEvidencePlan` and `benchmark_market_series_evidence_plan(...)` to
`benchmark_market_series.py`, then routed `IntegrationService.get_benchmark_market_series(...)`
through the plan before scheduling repository reads.

The service still owns repository call sequencing and async result collection, while the benchmark
market-series module now owns reusable field-to-evidence selection policy. Focused helper coverage
locks optional market-family reads and identity-FX suppression.

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
