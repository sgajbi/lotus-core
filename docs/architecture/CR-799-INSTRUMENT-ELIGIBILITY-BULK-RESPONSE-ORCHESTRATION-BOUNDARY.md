# CR-799 Instrument Eligibility Bulk Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_instrument_eligibility_bulk(...)` in the query-service instrument
eligibility boundary.

## Finding

Instrument eligibility bulk response assembly already lived in `instrument_eligibility.py`, but
the broad integration service still coordinated instrument eligibility repository lookup and
response assembly inline.

That kept RFC-087 instrument eligibility supportability workflow ownership split across the
integration service and the owning instrument eligibility module.

## Action

Added `resolve_instrument_eligibility_bulk_response(...)` to `instrument_eligibility.py` and
routed `IntegrationService.resolve_instrument_eligibility_bulk(...)` through that resolver with the
existing reference repository dependency.

The service still owns dependency wiring. The instrument eligibility module now owns the full
response workflow after dependency injection: eligibility read predicates, request-order
preservation, missing-security supportability, lineage, data-quality posture, runtime metadata, and
response assembly. Focused helper coverage locks repository read arguments and missing-security
behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\instrument_eligibility.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_integration_service.py
python -m ruff format --check src\services\query_service\app\services\instrument_eligibility.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_integration_service.py
git diff --check
```
