# CR-791 Risk-Free Coverage Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_risk_free_coverage(...)` in the market/reference source-data product path.

## Finding

Risk-free coverage response assembly already lived in `risk_free_coverage.py`, but the broad
integration service still coordinated currency normalization, repository lookup, and response
assembly inline.

That kept market-reference coverage workflow policy split across the integration service and the
owning risk-free coverage module.

## Action

Added `resolve_risk_free_coverage_response(...)` to `risk_free_coverage.py` and routed
`IntegrationService.get_risk_free_coverage(...)` through that resolver with the existing reference
repository dependency.

The service still owns dependency wiring. The risk-free coverage module now owns the full response
workflow after dependency injection: canonical currency normalization, repository read predicates,
and response assembly. Focused helper coverage locks normalized repository read arguments and
coverage response generation.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_risk_free_coverage.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\risk_free_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_coverage.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\risk_free_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_coverage.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
