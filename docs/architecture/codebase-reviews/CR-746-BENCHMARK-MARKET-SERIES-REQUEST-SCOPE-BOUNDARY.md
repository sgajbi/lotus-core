# CR-746 Benchmark Market Series Request Scope Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-series source-data
product path.

## Finding

Benchmark market-series request fingerprinting, page-size resolution, cursor extraction, and page
token scope validation were still embedded in the broad integration service.

That kept deterministic paging identity policy coupled to repository orchestration, even though
benchmark market-series response construction already lived in a focused helper module.

## Action

Added benchmark market-series request-scope and next-page token payload helpers to
`benchmark_market_series.py`.

The service now decodes the opaque token, delegates request-scope validation and page policy, then
uses the resulting scope for sequential repository reads and token encoding. Focused helper
coverage locks request fingerprint generation, requested-field normalization, page-size extraction,
cursor binding, mismatch rejection, and next-page payload shape.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter operator commands, migration policy, or published
database runbooks.

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
