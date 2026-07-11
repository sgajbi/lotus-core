# CR-1412 Transaction Economics Integration Family

## Status

Superseded by CR-1523 on 2026-07-11. The transitional Query Service family and compatibility
delegates described below were removed after QCP assumed end-to-end ownership.

## Scope

`IntegrationService` transaction-cost and performance-economics source-data products in
`query_service`.

## Finding

GitHub issue #548 remains valid: `IntegrationService` still carried source-data product families as
direct facade methods. The transaction economics path already had focused resolver modules for
transaction cost curves and performance component economics, but the facade still owned
transaction-repository access and page-token wiring for both products.

That kept transaction-economics orchestration coupled to unrelated integration dependencies and
made page-token behavior harder to test without the full facade.

## Action

Added `TransactionEconomicsIntegrationService` as the transaction economics contract-family
boundary. The family service owns transaction-repository provider access and page-token adapter
wiring for:

1. `TransactionCostCurve`
2. `PerformanceComponentEconomics`

`IntegrationService` now constructs the family service from its existing dependency bundle and keeps
the public facade methods as thin compatibility delegates.

## Compatibility

No downstream API contract changes are intended in this slice. Existing route handlers and service
callers continue to use the same facade methods and DTO contracts. Transaction cost curve paging,
performance component economics paging, request-scope fingerprints, supportability, lineage,
data-quality status, source-data product names, and repository read semantics are unchanged.

## Remaining Issue Scope

This is a partial issue #548 slice. Additional contract-family extractions are still needed before
the issue should be marked fixed-local, including benchmark/reference products, client
profile/income products, and remaining market/reference families.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_service.py tests\unit\services\query_service\services\test_performance_component_economics.py -q
python -m ruff check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\transaction_economics_integration_service.py tests\unit\services\query_service\services\test_integration_service.py tests\unit\services\query_service\services\test_performance_component_economics.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\transaction_economics_integration_service.py tests\unit\services\query_service\services\test_integration_service.py tests\unit\services\query_service\services\test_performance_component_economics.py
python -m mypy src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\transaction_economics_integration_service.py
git diff --check
```
