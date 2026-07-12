# CR-763 DPM Source Readiness Model Targets Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still decided inline whether the resolved model portfolio identity
was present before attempting the downstream model-target source read.

That kept optional model-target read policy in the broad integration service instead of the DPM
readiness module that owns missing model identity and unavailable model-target evidence semantics.

## Action

Added `dpm_source_model_targets_read_or_none(...)` to `dpm_source_readiness.py`, then routed the
service through that helper before resolving the model-target source-family outcome.

The service still owns source call ordering and the concrete model-target read dependency. The DPM
readiness module now owns reusable missing-identity read suppression and fail-closed model-target
read behavior. Focused helper coverage locks missing identity no-op behavior, resolved identity read
passthrough, and unavailable-source suppression.

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
