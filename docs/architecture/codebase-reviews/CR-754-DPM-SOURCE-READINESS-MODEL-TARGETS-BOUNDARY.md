# CR-754 DPM Source Readiness Model Targets Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still interpreted model-target outcomes inline: missing model
portfolio identity, failed model-target reads, and successful target-universe extraction each
directly appended source-family readiness in the broad integration service.

That kept DPM model-target readiness vocabulary and target-universe extraction policy coupled to the
service instead of the DPM readiness module that owns source-family supportability.

## Action

Added `DpmSourceModelTargetsResolution` and `dpm_source_model_targets_resolution(...)` to
`dpm_source_readiness.py`, then routed the service through that outcome boundary after the optional
model-target repository read.

The service still owns whether and how to call the model-target resolver, while the DPM readiness
module now owns reusable outcome-to-family mapping and target-instrument extraction. Focused helper
coverage locks missing model identity, unavailable target evidence, and ready target-universe
extraction.

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
