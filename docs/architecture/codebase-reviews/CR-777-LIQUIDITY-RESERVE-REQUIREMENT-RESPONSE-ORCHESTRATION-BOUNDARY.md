# CR-777 Liquidity Reserve Requirement Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_liquidity_reserve_requirement(...)` in the DPM/client source-data product
path.

## Finding

Liquidity reserve requirement orchestration still coordinated mandate binding resolution,
missing-binding short-circuit behavior, liquidity reserve repository reads, and response assembly
inline in the broad integration service.

That left the integration service as the owner of liquidity reserve workflow policy even though the
liquidity reserve module already owned reserve mapping, supportability, lineage, source-batch
fingerprinting, snapshot identity, and runtime metadata.

## Action

Added `resolve_liquidity_reserve_requirement_response(...)` to
`liquidity_reserve_requirement.py`, then routed
`IntegrationService.get_liquidity_reserve_requirement(...)` through that helper with the existing
reference repository dependency.

The service still owns dependency wiring. The liquidity reserve module now owns the full source-data
response workflow after dependency injection: mandate binding resolution, missing-binding
short-circuiting, reserve repository read arguments, and response assembly. Focused helper coverage
locks repository read arguments, read order, and no-reserve-read behavior when mandate binding is
unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_liquidity_reserve_requirement.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\liquidity_reserve_requirement.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_liquidity_reserve_requirement.py
python -m ruff format --check src\services\query_service\app\services\liquidity_reserve_requirement.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_liquidity_reserve_requirement.py
git diff --check
```
