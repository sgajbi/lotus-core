# CR-717 Model Portfolio Target Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_model_portfolio_targets(...)` in the DPM source-data product support
path.

## Finding

Model portfolio target resolution is a core DPM source-data product, but response assembly was still
embedded in the integration service. Target row mapping, total-weight supportability, lineage, and
runtime metadata lived beside repository orchestration.

That shape made the model-target evidence contract harder to audit and reuse from DPM readiness
flows.

## Action

Added `model_portfolio_targets.py` as the focused model-target response boundary.

The service now resolves the model definition, reads target rows for the resolved version, and
delegates response assembly. Focused helper coverage locks ready, degraded, and empty-target
supportability plus data-quality status, latest evidence timestamp, and lineage.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

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
