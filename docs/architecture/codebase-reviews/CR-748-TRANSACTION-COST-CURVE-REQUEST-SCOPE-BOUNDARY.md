# CR-748 Transaction Cost Curve Request Scope Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_transaction_cost_curve(...)` in the DPM transaction-cost evidence path.

## Finding

Transaction cost curve request fingerprinting, cursor extraction, page token scope validation, and
next-page token payload construction were still embedded in the broad integration service.

That kept deterministic paging identity policy coupled to transaction repository orchestration,
despite transaction cost grouping, curve construction, response assembly, and supportability policy
already being helper-owned.

## Action

Added transaction cost curve request-scope and next-page token payload helpers to
`transaction_cost_curve.py`.

The service now decodes the opaque page token, delegates request-scope validation and cursor
mapping, then uses the resulting scope for page construction and token encoding. Focused helper
coverage locks filter fingerprinting, curve-key cursor binding, token mismatch rejection, and
last-curve-point next-page payload shape.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter operator commands, migration policy, or published
database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_transaction_cost_curve.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\transaction_cost_curve.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_transaction_cost_curve.py
python -m ruff format --check src\services\query_service\app\services\transaction_cost_curve.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_transaction_cost_curve.py
git diff --check
```
