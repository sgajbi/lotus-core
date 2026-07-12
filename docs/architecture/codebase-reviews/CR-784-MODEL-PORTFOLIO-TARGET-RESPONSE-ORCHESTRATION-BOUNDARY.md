# CR-784 Model Portfolio Target Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_model_portfolio_targets(...)` in the DPM model source-data product path.

## Finding

Model portfolio target orchestration still coordinated model definition resolution,
missing-definition short-circuit behavior, model target repository reads, and response assembly
inline in the broad integration service.

That left the integration service as the owner of model target workflow policy even though the model
portfolio target module already owned target mapping, supportability, lineage, evidence timestamp
selection, data quality status, and runtime metadata.

## Action

Added `resolve_model_portfolio_target_response(...)` to `model_portfolio_targets.py`, then routed
`IntegrationService.resolve_model_portfolio_targets(...)` through that helper with the existing
reference repository dependency.

The service still owns dependency wiring and remains the stable reader injected into DPM source
readiness. The model portfolio target module now owns the full source-data response workflow after
dependency injection: definition resolution, missing-definition short-circuiting, target repository
read arguments, and response assembly. Focused helper coverage locks repository read arguments,
read order, and no-target-read behavior when the model definition is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_model_portfolio_targets.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\model_portfolio_targets.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_model_portfolio_targets.py
python -m ruff format --check src\services\query_service\app\services\model_portfolio_targets.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_model_portfolio_targets.py
git diff --check
```
