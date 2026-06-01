# CR-772 Transaction Cost Curve Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_transaction_cost_curve(...)` in the transaction-cost source-data path.

## Finding

Transaction cost-curve orchestration still coordinated portfolio existence validation, request-scope
binding, transaction-cost evidence reads, curve page construction, page-token creation, and response
assembly inline in the broad integration service.

That left the integration service as the owner of transaction cost-curve workflow policy even
though the transaction cost-curve module already owned grouping, paging, supportability, and
lineage semantics.

## Action

Added `resolve_transaction_cost_curve_response(...)` to `transaction_cost_curve.py`, then routed
`IntegrationService.get_transaction_cost_curve(...)` through that helper with the existing
transaction repository and page-token codec dependencies.

The service still owns dependency wiring. The transaction cost-curve module now owns the full
source-data response workflow after dependency injection: portfolio validation, page-token scope
validation, repository evidence read arguments, curve page construction, next-page token creation,
and response assembly. Focused helper coverage locks repository read order, source read arguments,
encoded token payload shape, returned page shape, and missing-portfolio behavior.

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
