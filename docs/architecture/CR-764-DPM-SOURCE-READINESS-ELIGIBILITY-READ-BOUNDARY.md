# CR-764 DPM Source Readiness Eligibility Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still decided inline whether the evaluated instrument universe was
empty before attempting the downstream instrument-eligibility source read.

That kept optional eligibility read policy in the broad integration service instead of the DPM
readiness module that owns empty-universe and unavailable eligibility evidence semantics.

## Action

Added `dpm_source_eligibility_read_or_none(...)` to `dpm_source_readiness.py`, then routed the
service through that helper before resolving the eligibility source-family outcome.

The service still owns source call ordering and the concrete eligibility resolver dependency. The
DPM readiness module now owns reusable empty-universe read suppression and fail-closed eligibility
read behavior. Focused helper coverage locks empty universe no-op behavior, evaluated-universe read
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
