# CR-785 CIO Model Change Cohort Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_cio_model_change_affected_cohort(...)` in the CIO model-change
source-data product path.

## Finding

CIO model-change cohort orchestration still coordinated model definition resolution,
missing-definition short-circuit behavior, affected mandate repository reads, and response assembly
inline in the broad integration service.

That left the integration service as the owner of CIO model-change workflow policy even though the
CIO model-change cohort module already owned affected-mandate mapping, supportability, lineage,
source-batch fingerprinting, event identity, snapshot identity, and runtime metadata.

## Action

Added `resolve_cio_model_change_affected_cohort_response(...)` to
`cio_model_change_cohort.py`, then routed
`IntegrationService.resolve_cio_model_change_affected_cohort(...)` through that helper with the
existing reference repository dependency.

The service still owns dependency wiring. The CIO model-change cohort module now owns the full
source-data response workflow after dependency injection: model definition resolution,
missing-definition short-circuiting, affected mandate repository read arguments, and response
assembly. Focused helper coverage locks repository read arguments, read order, and
no-affected-mandate-read behavior when the model definition is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_cio_model_change_cohort.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\cio_model_change_cohort.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_cio_model_change_cohort.py
python -m ruff format --check src\services\query_service\app\services\cio_model_change_cohort.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_cio_model_change_cohort.py
git diff --check
```
