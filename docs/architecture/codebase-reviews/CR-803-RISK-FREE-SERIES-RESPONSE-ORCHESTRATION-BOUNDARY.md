# CR-803 Risk-Free Series Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_risk_free_series(...)` in the query-service market reference risk-free
series boundary.

## Finding

Risk-free series response assembly already lived in `risk_free_series.py`, but the broad
integration service still coordinated currency normalization, risk-free repository lookup, and
response assembly inline.

That kept RFC-062 risk-free series workflow ownership split across the integration service and the
owning risk-free series module, while the adjacent risk-free coverage path already used an owned
resolver boundary.

## Action

Added `resolve_risk_free_series_response(...)` to `risk_free_series.py` and routed
`IntegrationService.get_risk_free_series(...)` through that resolver with the existing reference
repository dependency.

The service still owns dependency wiring. The risk-free series module now owns the full response
workflow after dependency injection: currency normalization, risk-free series read predicates,
request fingerprint scope, resolved window, point mapping, lineage, data-quality posture, runtime
metadata, and response assembly. Focused helper coverage locks normalized repository read
arguments and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_risk_free_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\risk_free_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_series.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\risk_free_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_series.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
