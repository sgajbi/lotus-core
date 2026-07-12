# CR-753 DPM Source Readiness Identity Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still resolved mandate and model-portfolio identity inline:
caller-provided mandate/model ids seeded the response identity, a resolved mandate replaced the
mandate id, and the mandate model portfolio supplied a fallback only when the caller did not provide
an explicit model portfolio id.

That kept DPM readiness identity precedence coupled to the broad integration service instead of the
DPM readiness module that owns source-family supportability and response identity.

## Action

Added `DpmSourceReadinessIdentity`, `dpm_source_initial_identity(...)`, and
`dpm_source_identity_from_mandate(...)` to `dpm_source_readiness.py`, then routed the service through
that identity boundary.

The service still owns repository call sequencing and fail-closed orchestration, while the DPM
readiness module now owns reusable request-vs-mandate identity precedence. Focused helper coverage
locks caller scope preservation, explicit model override behavior, and mandate-model fallback.

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
