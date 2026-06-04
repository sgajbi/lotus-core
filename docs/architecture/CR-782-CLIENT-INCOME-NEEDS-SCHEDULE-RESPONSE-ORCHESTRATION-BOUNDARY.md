# CR-782 Client Income Needs Schedule Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_income_needs_schedule(...)` in the client income source-data product
path.

## Finding

Client income needs schedule orchestration still coordinated mandate binding resolution,
missing-binding short-circuit behavior, client income schedule repository reads, and response
assembly inline in the broad integration service.

That left the integration service as the owner of client income workflow policy even though the
client income needs schedule module already owned schedule mapping, supportability, lineage,
source-batch fingerprinting, snapshot identity, and runtime metadata.

## Action

Added `resolve_client_income_needs_schedule_response(...)` to `client_income_needs_schedule.py`,
then routed `IntegrationService.get_client_income_needs_schedule(...)` through that helper with the
existing reference repository dependency.

The service still owns dependency wiring. The client income needs schedule module now owns the full
source-data response workflow after dependency injection: mandate binding resolution,
missing-binding short-circuiting, income schedule repository read arguments, and response assembly.
Focused helper coverage locks repository read arguments, read order, and no-income-schedule-read
behavior when mandate binding is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_client_income_needs_schedule.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\client_income_needs_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_income_needs_schedule.py
python -m ruff format --check src\services\query_service\app\services\client_income_needs_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_income_needs_schedule.py
git diff --check
```
