# CR-724 Client Tax Profile Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_tax_profile(...)` in the DPM/client source-data product support
path.

## Finding

Client tax profile resolution is a core private-banking tax-aware construction input, but response
assembly was still embedded in the integration service. Tax profile DTO mapping, empty-profile
supportability, lineage, source-batch fingerprinting, snapshot identity, and runtime metadata lived
beside mandate binding resolution and tax-profile repository reads.

That made tax-aware construction evidence harder to audit and kept the client profile source-data
family inconsistent with the extracted restriction and sustainability profile boundaries.

## Action

Added `client_tax_profile.py` as the focused client tax profile response boundary.

The service now resolves the mandate binding, reads effective tax profile rows, and delegates
response assembly. Focused helper coverage locks ready and empty-profile supportability, tax profile
mapping, latest evidence timestamp selection across binding and profile evidence, lineage,
data-quality status, source-batch fingerprinting, and snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_client_tax_profile.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\client_tax_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_tax_profile.py
python -m ruff format --check src\services\query_service\app\services\client_tax_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_tax_profile.py
git diff --check
```
