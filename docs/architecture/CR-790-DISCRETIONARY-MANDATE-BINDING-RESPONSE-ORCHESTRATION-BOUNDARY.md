# CR-790 Discretionary Mandate Binding Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_discretionary_mandate_binding(...)` in the DPM mandate source-data
product path.

## Finding

Discretionary mandate binding response assembly already lived in
`discretionary_mandate_binding.py`, but the broad integration service still coordinated the
effective mandate-binding repository lookup, optional mandate and booking-center predicates, missing
binding short-circuit behavior, and response assembly.

That kept foundational DPM mandate-binding workflow policy split across the integration service and
the owning mandate-binding module.

## Action

Added `resolve_discretionary_mandate_binding_response(...)` to
`discretionary_mandate_binding.py` and routed
`IntegrationService.resolve_discretionary_mandate_binding(...)` through that resolver with the
existing reference repository dependency.

The service still owns dependency wiring. The mandate-binding module now owns the full response
workflow after dependency injection: repository read predicates, missing-binding behavior, and
response assembly. Focused helper coverage locks repository read arguments and the missing-binding
`None` path.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_discretionary_mandate_binding.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\discretionary_mandate_binding.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_discretionary_mandate_binding.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\discretionary_mandate_binding.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_discretionary_mandate_binding.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
