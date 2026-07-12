# CR-722 Client Restriction Profile Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_restriction_profile(...)` in the DPM/client source-data product
support path.

## Finding

Client restriction profile resolution is a core private-banking suitability and product-governance
input, but response assembly was still embedded in the integration service. Restriction DTO
mapping, empty-profile supportability, lineage, source-batch fingerprinting, snapshot identity, and
runtime metadata lived beside mandate binding resolution and restriction repository reads.

That made restriction-aware DPM construction policy harder to audit and reuse across source-data
readiness and client profile flows.

## Action

Added `client_restriction_profile.py` as the focused client restriction response boundary.

The service now resolves the mandate binding, reads effective restriction rows, and delegates
response assembly. Focused helper coverage locks ready and empty-profile supportability,
restriction mapping, latest evidence timestamp selection across binding and restriction evidence,
lineage, data-quality status, source-batch fingerprinting, and snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_client_restriction_profile.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\client_restriction_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_restriction_profile.py
python -m ruff format --check src\services\query_service\app\services\client_restriction_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_restriction_profile.py
git diff --check
```
