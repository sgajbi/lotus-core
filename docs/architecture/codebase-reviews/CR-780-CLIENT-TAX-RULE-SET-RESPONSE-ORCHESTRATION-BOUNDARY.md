# CR-780 Client Tax Rule Set Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_tax_rule_set(...)` in the client tax source-data product path.

## Finding

Client tax rule-set orchestration still coordinated mandate binding resolution, missing-binding
short-circuit behavior, client tax rule repository reads, and response assembly inline in the broad
integration service.

That left the integration service as the owner of client tax rule workflow policy even though the
client tax rule-set module already owned tax-rule mapping, supportability, lineage, source-batch
fingerprinting, snapshot identity, and runtime metadata.

## Action

Added `resolve_client_tax_rule_set_response(...)` to `client_tax_rule_set.py`, then routed
`IntegrationService.get_client_tax_rule_set(...)` through that helper with the existing reference
repository dependency.

The service still owns dependency wiring. The client tax rule-set module now owns the full
source-data response workflow after dependency injection: mandate binding resolution,
missing-binding short-circuiting, tax-rule repository read arguments, and response assembly.
Focused helper coverage locks repository read arguments, read order, and no-tax-rule-read behavior
when mandate binding is unavailable.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_client_tax_rule_set.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\client_tax_rule_set.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_tax_rule_set.py
python -m ruff format --check src\services\query_service\app\services\client_tax_rule_set.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_tax_rule_set.py
git diff --check
```
