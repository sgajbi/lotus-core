# CR-727 Liquidity Reserve Requirement Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_liquidity_reserve_requirement(...)` in the DPM/client source-data product
support path.

## Finding

Liquidity reserve requirements are private-banking reserve evidence used by downstream DPM support
flows, but response assembly was still embedded in the integration service. Requirement DTO mapping,
empty requirement supportability, lineage, source-batch fingerprinting, snapshot identity, and
runtime metadata lived beside mandate binding resolution and reserve repository reads.

That made reserve evidence harder to audit and kept the income, reserve, and withdrawal source-data
family inconsistent as the surrounding DPM evidence boundaries were being extracted.

## Action

Added `liquidity_reserve_requirement.py` as the focused reserve requirement response boundary.

The service now resolves the mandate binding, reads effective reserve requirement rows, and delegates
response assembly. Focused helper coverage locks ready and empty-requirement supportability,
requirement mapping, latest evidence timestamp selection across binding and reserve evidence,
lineage, data-quality status, source-batch fingerprinting, and snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_liquidity_reserve_requirement.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\liquidity_reserve_requirement.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_liquidity_reserve_requirement.py
python -m ruff format --check src\services\query_service\app\services\liquidity_reserve_requirement.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_liquidity_reserve_requirement.py
git diff --check
```
