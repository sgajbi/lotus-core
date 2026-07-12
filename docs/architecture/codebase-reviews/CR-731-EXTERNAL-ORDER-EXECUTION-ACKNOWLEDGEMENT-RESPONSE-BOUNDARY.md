# CR-731 External Order Execution Acknowledgement Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_external_order_execution_acknowledgement(...)` in the external OMS
source-data product support path.

## Finding

External order execution acknowledgement is intentionally fail-closed until bank-owned OMS
acknowledgement ingestion is certified, but the unavailable response posture was assembled inline in
the integration service. Missing OMS evidence families, blocked non-claim capabilities, empty
acknowledgement rows, lineage, fingerprinting, snapshot identity, and runtime metadata lived beside
mandate binding resolution.

That made the OMS acknowledgement boundary harder to audit and increased the risk that downstream
`lotus-manage` execution support work could accidentally imply order generation, venue routing,
best execution, fills, settlement, or autonomous execution capability.

## Action

Added `external_order_execution_acknowledgement.py` as the focused fail-closed OMS acknowledgement
response boundary.

The service now resolves the mandate binding and delegates unavailable response assembly. Focused
helper coverage locks missing OMS source families, blocked non-claim capabilities, empty
acknowledgement rows, lineage, data-quality status, sorted order-reference fingerprinting, and
deterministic snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_external_order_execution_acknowledgement.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\external_order_execution_acknowledgement.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_order_execution_acknowledgement.py
python -m ruff format --check src\services\query_service\app\services\external_order_execution_acknowledgement.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_order_execution_acknowledgement.py
git diff --check
```
