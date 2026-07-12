# CR-798 Classification Taxonomy Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_classification_taxonomy(...)` in the query-service market reference
taxonomy boundary.

## Finding

Classification taxonomy response assembly already lived in `classification_taxonomy.py`, but the
broad integration service still coordinated taxonomy repository lookup and response assembly
inline.

That kept market-reference taxonomy workflow ownership split across the integration service and
the owning classification taxonomy module.

## Action

Added `resolve_classification_taxonomy_response(...)` to `classification_taxonomy.py` and routed
`IntegrationService.get_classification_taxonomy(...)` through that resolver with the existing
reference repository dependency.

The service still owns dependency wiring. The classification taxonomy module now owns the full
response workflow after dependency injection: taxonomy read predicates, request fingerprint scope,
runtime metadata, data-quality posture, and response assembly. Focused helper coverage locks
repository read arguments and response behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_classification_taxonomy.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\classification_taxonomy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_classification_taxonomy.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\classification_taxonomy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_classification_taxonomy.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
