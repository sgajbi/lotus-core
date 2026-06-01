# CR-755 DPM Source Readiness Eligibility Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still interpreted eligibility outcomes inline: an empty
evaluated instrument universe, failed eligibility evidence read, and successful eligibility
supportability each directly selected a source-family readiness payload in the broad integration
service.

That kept DPM eligibility readiness vocabulary and fail-closed missing-item policy coupled to the
service instead of the DPM readiness module that owns source-family supportability.

## Action

Added `dpm_source_eligibility_family(...)` to `dpm_source_readiness.py`, then routed the service
through that outcome boundary after the optional eligibility read.

The service still owns whether and how to call the eligibility resolver, while the DPM readiness
module now owns reusable eligibility outcome-to-family mapping. Focused helper coverage locks empty
instrument-universe behavior, capped missing-item samples for unavailable eligibility evidence, and
source supportability preservation.

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
