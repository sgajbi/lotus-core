# CR-760 Benchmark Market Series Index Page Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-series path.

## Finding

Benchmark market-series orchestration still interpreted the over-fetched component index identifier
list inline by slicing it to the requested page size and deriving `has_more` from the extra row.

That kept index-page window semantics in the broad integration service instead of the benchmark
market-series module that owns request identity, page-token policy, and page metadata.

## Action

Added `BenchmarkMarketSeriesIndexPage` and `benchmark_market_series_index_page(...)` to
`benchmark_market_series.py`, then routed repository evidence reads, token generation, and response
assembly through the resolved page object.

The service still owns the repository query and over-fetch limit, while the benchmark market-series
module now owns reusable page capping and terminal/non-terminal page classification. Focused helper
coverage locks capped page behavior and terminal-page classification.

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
