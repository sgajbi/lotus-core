# CR-776 Planned Withdrawal Schedule Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_planned_withdrawal_schedule(...)` in the DPM/client source-data product path.

## Finding

Planned withdrawal schedule orchestration still coordinated mandate binding resolution,
missing-binding short-circuit behavior, planned-withdrawal repository reads, and response assembly
inline in the broad integration service.

That left the integration service as the owner of planned-withdrawal workflow policy even though
the planned withdrawal module already owned withdrawal mapping, supportability, lineage, source-batch
fingerprinting, snapshot identity, and runtime metadata.

## Action

Added `resolve_planned_withdrawal_schedule_response(...)` to `planned_withdrawal_schedule.py`, then
routed `IntegrationService.get_planned_withdrawal_schedule(...)` through that helper with the
existing reference repository dependency.

The service still owns dependency wiring. The planned withdrawal module now owns the full source-data
response workflow after dependency injection: mandate binding resolution, missing-binding
short-circuiting, withdrawal repository read arguments, and response assembly. Focused helper
coverage locks repository read arguments, read order, and no-withdrawal-read behavior when mandate
binding is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_planned_withdrawal_schedule.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\planned_withdrawal_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_planned_withdrawal_schedule.py
python -m ruff format --check src\services\query_service\app\services\planned_withdrawal_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_planned_withdrawal_schedule.py
git diff --check
```
