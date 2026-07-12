# CR-804 Effective Integration Policy Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_effective_policy(...)` in the query-service integration policy boundary.

## Finding

Effective integration policy response assembly and policy-context resolution already lived in
`integration_policy.py`, but the broad integration service still owned response timestamp
generation and called the builder directly.

That kept integration policy response orchestration split across the service and the owning policy
module.

## Action

Added `resolve_effective_policy_response(...)` to `integration_policy.py` and routed
`IntegrationService.get_effective_policy(...)` through that resolver.

The service now owns only request forwarding. The integration policy module owns the full response
workflow: consumer canonicalization, configured policy context, allowed-section filtering,
provenance, warning posture, timestamp generation, and response assembly. Focused helper coverage
locks timestamp ownership and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_policy.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\integration_policy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_integration_policy.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\integration_policy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_integration_policy.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
