# CR-779 Sustainability Preference Profile Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_sustainability_preference_profile(...)` in the client source-data product
path.

## Finding

Sustainability preference profile orchestration still coordinated mandate binding resolution,
missing-binding short-circuit behavior, sustainability preference repository reads, and response
assembly inline in the broad integration service.

That left the integration service as the owner of sustainability preference workflow policy even
though the sustainability preference profile module already owned preference mapping,
supportability, lineage, source-batch fingerprinting, snapshot identity, and runtime metadata.

## Action

Added `resolve_sustainability_preference_profile_response(...)` to
`sustainability_preference_profile.py`, then routed
`IntegrationService.get_sustainability_preference_profile(...)` through that helper with the
existing reference repository dependency.

The service still owns dependency wiring. The sustainability preference profile module now owns the
full source-data response workflow after dependency injection: mandate binding resolution,
missing-binding short-circuiting, preference repository read arguments, and response assembly.
Focused helper coverage locks repository read arguments, read order, and no-preference-read
behavior when mandate binding is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_sustainability_preference_profile.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\sustainability_preference_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_sustainability_preference_profile.py
python -m ruff format --check src\services\query_service\app\services\sustainability_preference_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_sustainability_preference_profile.py
git diff --check
```
