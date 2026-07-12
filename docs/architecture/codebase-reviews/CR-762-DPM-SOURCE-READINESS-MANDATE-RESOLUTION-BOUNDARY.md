# CR-762 DPM Source Readiness Mandate Resolution Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still interpreted the mandate binding read outcome inline by
branching between unavailable mandate evidence and resolved mandate/model identity.

That kept mandate-source outcome vocabulary in the broad integration service instead of the DPM
readiness module that owns source-family readiness and identity precedence policy.

## Action

Added `DpmSourceMandateResolution` and `dpm_source_mandate_resolution(...)` to
`dpm_source_readiness.py`, then routed the service through that outcome boundary after the optional
mandate read.

The service still owns source call ordering and request arguments, while the DPM readiness module now
owns reusable mandate identity and source-family outcome mapping. Focused helper coverage locks
unavailable mandate behavior, caller identity preservation, resolved mandate identity, and source
supportability passthrough.

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
