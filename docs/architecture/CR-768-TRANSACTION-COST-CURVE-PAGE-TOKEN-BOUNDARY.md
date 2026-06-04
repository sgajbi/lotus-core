# CR-768 Transaction Cost Curve Page Token Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_transaction_cost_curve(...)` in the transaction cost-curve path.

## Finding

Transaction cost-curve orchestration still converted next-page token payloads into encoded page
tokens inline after the request-scope and payload helpers had already resolved page identity policy.

That kept terminal/non-terminal token encoding behavior in the broad integration service instead of
the transaction cost-curve module that owns curve paging semantics.

## Action

Added `transaction_cost_curve_page_token(...)` to `transaction_cost_curve.py`, then routed the
service through that helper with the existing service encoder dependency.

The service still owns source read ordering and token encoder implementation. The transaction
cost-curve module now owns reusable next-page payload suppression and encoded-token passthrough.
Focused helper coverage locks encoded payload passthrough and terminal-page no-op encoding.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

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
