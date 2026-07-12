# CR-771 DPM Source Readiness Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still coordinated mandate binding reads, mandate identity
resolution, model-target reads, evaluated-instrument scope construction, eligibility reads,
tax-lot reads, market-data reads, family assembly, and response assembly inline in the broad
integration service.

That left the integration service as the owner of DPM source-readiness workflow policy even though
the DPM source-readiness module already owned family state, unavailable-source policy, request
builders, and supportability aggregation.

## Action

Added `DpmSourceReadinessReaders` and `resolve_dpm_source_readiness_response(...)` to
`dpm_source_readiness.py`, then routed `IntegrationService.get_dpm_source_readiness(...)` through
that helper with the existing service methods as injected readers.

The service still owns dependency wiring. The DPM source-readiness module now owns the full
source-family response workflow after dependency injection: source read ordering, fail-closed
unavailable-source handling, mandate/model identity resolution, evaluated universe composition,
request-scope construction for downstream source products, family assembly, and final response
assembly. Focused helper coverage locks read order, scoped request propagation, resolved identity,
evaluated universe, and ordered family output.

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
