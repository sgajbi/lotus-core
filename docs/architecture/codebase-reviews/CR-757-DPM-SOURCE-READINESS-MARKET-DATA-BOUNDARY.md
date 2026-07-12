# CR-757 DPM Source Readiness Market Data Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still interpreted market-data outcomes inline: failed market-data
coverage reads and successful market-data supportability each directly selected a source-family
readiness payload in the broad integration service.

That kept DPM market-data readiness vocabulary and combined missing/stale scope policy coupled to
the service instead of the DPM readiness module that owns source-family supportability.

## Action

Added `dpm_source_market_data_family(...)` to `dpm_source_readiness.py`, then routed the service
through that outcome boundary after the market-data coverage read attempt.

The service still owns the market-data coverage repository call and request scope, while the DPM
readiness module now owns reusable market-data outcome-to-family mapping. Focused helper coverage
locks unavailable market-data evidence behavior and source supportability preservation, including
combined missing and stale instrument/currency scope.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_dpm_source_readiness.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\dpm_source_readiness.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_source_readiness.py
python -m ruff format --check src\services\query_service\app\services\dpm_source_readiness.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_source_readiness.py
git diff --check
```
