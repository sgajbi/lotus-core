# CR-767 DPM Source Readiness Family Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still owned the ordered source-family list assembly inline after
each governed source read completed.

That kept the DPM family ordering policy and evaluated instrument scope construction split between
the broad integration service and the DPM readiness module.

## Action

Added `DpmSourceReadinessAssembly` and `dpm_source_readiness_assembly(...)` to
`dpm_source_readiness.py`, then routed final response assembly through that helper after the service
completes source reads in the existing order.

The service still owns source call sequencing and concrete dependencies. The DPM readiness module
now owns the ordered family list, evaluated instrument scope, and resolved identity payload used by
the final response mapper. Focused helper coverage locks family ordering, resolved identity
preservation, evaluated universe composition, and source-family supportability passthrough.

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
