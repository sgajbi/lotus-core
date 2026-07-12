# CR-761 Benchmark Market Series Evidence Factory Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_market_series(...)` in the benchmark market-series path.

## Finding

Benchmark market-series orchestration still assembled every repository evidence read factory inline,
including component window reads, index price reads, index return reads, benchmark return reads, and
FX rate reads.

That kept market-series repository read argument shape in the broad integration service instead of
the benchmark market-series module that owns evidence family planning and read collection policy.

## Action

Added `benchmark_market_series_evidence_read_factories(...)` to `benchmark_market_series.py`, then
routed the service through that helper before invoking `benchmark_market_series_read_evidence(...)`.

The service still owns the concrete repository dependency, benchmark id, resolved benchmark
currency, and resolved index page. The benchmark market-series module now owns reusable construction
of evidence-family repository call boundaries. Focused helper coverage locks all repository read
arguments for component, index price, index return, benchmark return, and FX rate evidence.

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
