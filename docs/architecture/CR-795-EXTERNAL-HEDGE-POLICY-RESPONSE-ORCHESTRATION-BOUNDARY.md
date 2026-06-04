# CR-795 External Hedge Policy Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_external_hedge_policy(...)` in the external treasury source-data product
boundary.

## Finding

External hedge policy response assembly already lived in `external_hedge_policy.py`, but the broad
integration service still coordinated mandate-binding lookup, optional mandate predicates,
missing-binding short-circuit behavior, and response assembly inline.

That kept fail-closed external treasury workflow policy split across the integration service and
the owning external hedge policy module.

## Action

Added `resolve_external_hedge_policy_response(...)` to `external_hedge_policy.py` and routed
`IntegrationService.get_external_hedge_policy(...)` through that resolver with the existing
reference repository dependency.

The service still owns dependency wiring. The external hedge policy module now owns the full
response workflow after dependency injection: mandate-binding read predicates, missing-binding
behavior, and fail-closed response assembly. Focused helper coverage locks repository read
arguments and the missing-binding `None` path.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_external_hedge_policy.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\external_hedge_policy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_hedge_policy.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\external_hedge_policy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_hedge_policy.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
