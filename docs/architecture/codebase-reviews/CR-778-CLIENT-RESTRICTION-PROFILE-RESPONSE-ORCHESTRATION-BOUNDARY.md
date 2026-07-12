# CR-778 Client Restriction Profile Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_restriction_profile(...)` in the client source-data product path.

## Finding

Client restriction profile orchestration still coordinated mandate binding resolution,
missing-binding short-circuit behavior, client restriction repository reads, and response assembly
inline in the broad integration service.

That left the integration service as the owner of client restriction workflow policy even though the
client restriction profile module already owned restriction mapping, supportability, lineage,
source-batch fingerprinting, snapshot identity, and runtime metadata.

## Action

Added `resolve_client_restriction_profile_response(...)` to `client_restriction_profile.py`, then
routed `IntegrationService.get_client_restriction_profile(...)` through that helper with the
existing reference repository dependency.

The service still owns dependency wiring. The client restriction profile module now owns the full
source-data response workflow after dependency injection: mandate binding resolution,
missing-binding short-circuiting, restriction repository read arguments, and response assembly.
Focused helper coverage locks repository read arguments, read order, and no-restriction-read
behavior when mandate binding is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_client_restriction_profile.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\client_restriction_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_restriction_profile.py
python -m ruff format --check src\services\query_service\app\services\client_restriction_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_restriction_profile.py
git diff --check
```
