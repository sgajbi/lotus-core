# CR-759 Benchmark Market Series Currency Token Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-series path.

## Finding

Benchmark market-series orchestration still resolved benchmark currency fallback and encoded the
next-page token inline after the request-scope boundary had already produced token payload policy.

That kept currency resolution and token encoding policy in the broad integration service instead of
the benchmark market-series module that owns market-series request identity and paging semantics.

## Action

Added `benchmark_market_series_currency(...)` and `benchmark_market_series_page_token(...)` to
`benchmark_market_series.py`, then routed the service through those helpers.

The service still owns repository read sequencing and the concrete page-token encoder dependency,
while the benchmark market-series module now owns reusable currency fallback and terminal-page token
suppression policy. Focused helper coverage locks definition-first currency precedence,
target-currency fallback, unknown-currency fallback, encoded payload passthrough, and no-op encoding
for terminal pages.

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
