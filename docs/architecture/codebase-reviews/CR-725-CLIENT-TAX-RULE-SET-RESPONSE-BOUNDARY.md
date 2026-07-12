# CR-725 Client Tax Rule Set Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_tax_rule_set(...)` in the DPM/client source-data product support
path.

## Finding

Client tax rule-set resolution is a core private-banking tax-aware construction input, but response
assembly was still embedded in the integration service. Tax rule DTO mapping, empty rule-set
supportability, lineage, source-batch fingerprinting, snapshot identity, and runtime metadata lived
beside mandate binding resolution and tax-rule repository reads.

That made tax-aware rule evidence harder to audit and kept the tax source-data family inconsistent
with the extracted tax profile boundary.

## Action

Added `client_tax_rule_set.py` as the focused client tax rule-set response boundary.

The service now resolves the mandate binding, reads effective tax rule rows, and delegates response
assembly. Focused helper coverage locks ready and empty-rule-set supportability, rule mapping,
latest evidence timestamp selection across binding and rule evidence, lineage, data-quality status,
source-batch fingerprinting, and snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

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
