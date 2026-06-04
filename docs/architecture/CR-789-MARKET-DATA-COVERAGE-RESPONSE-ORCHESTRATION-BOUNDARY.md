# CR-789 Market Data Coverage Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_market_data_coverage(...)` in the DPM market/reference source-data product
path.

## Finding

Market-data coverage response assembly already lived in `market_data_coverage.py`, but the broad
integration service still coordinated read-scope construction, latest market-price reads, latest
FX-rate reads, and response assembly.

That left source-data product workflow policy split across the integration service and the owning
market-data coverage module. It also made the prior parallel-read performance expectation harder to
prove at the helper boundary.

## Action

Added `resolve_market_data_coverage_response(...)` to `market_data_coverage.py` and routed
`IntegrationService.get_market_data_coverage(...)` through that resolver with the existing
reference repository dependency.

The service still owns dependency wiring. The market-data coverage module now owns request-scope
normalization, deduplicated repository predicates, parallel latest-price/latest-FX evidence reads,
and response assembly. Focused helper coverage proves deduplicated read arguments, preserved
requested counts, and parallel read startup.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization and performance-boundary hardening step and does not alter API shape, operator
commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_market_data_coverage.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\market_data_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_market_data_coverage.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\market_data_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_market_data_coverage.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
