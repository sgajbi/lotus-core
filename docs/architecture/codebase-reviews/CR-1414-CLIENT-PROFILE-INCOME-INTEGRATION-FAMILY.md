# CR-1414 Client Profile Income Integration Family

## Status

In progress on 2026-07-06.

## Scope

`IntegrationService` client profile, suitability, tax, income, liquidity reserve, and planned
withdrawal source-data products in `query_service`.

## Finding

GitHub issue #548 remains valid: `IntegrationService` still carried client profile and income
source-data product orchestration as direct facade methods. The response assembly and supportability
policy already lived in focused resolver modules, but the facade still owned reference-repository
access for client restriction profiles, sustainability preferences, client tax profiles, tax rule
sets, income needs schedules, liquidity reserve requirements, and planned withdrawal schedules.

That kept client suitability/income product orchestration coupled to unrelated integration
dependencies and made the family harder to test without the full facade.

## Action

Added `ClientProfileIncomeIntegrationService` as the client profile/income contract-family boundary.
The family service owns reference-repository provider access while delegating to the existing
resolver modules.

`IntegrationService` now constructs the family service from its existing dependency bundle and keeps
the public facade methods as thin compatibility delegates.

## Compatibility

No downstream API contract changes are intended in this slice. Existing route handlers and service
callers continue to use the same facade methods and DTO contracts. Portfolio-to-client mandate
binding, client identifiers, supportability states, missing-data families, lineage, source-data
product names, snapshot identities, source-table names, repository SQL, database schema, and runtime
topology are unchanged.

## Remaining Issue Scope

This is a partial issue #548 slice. Additional contract-family extraction is still needed before the
issue should be marked fixed-local, including remaining DPM portfolio-management reference products.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_service.py -q
python -m ruff check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\client_profile_income_integration_service.py tests\unit\services\query_service\services\test_integration_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\client_profile_income_integration_service.py tests\unit\services\query_service\services\test_integration_service.py
python -m mypy src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\client_profile_income_integration_service.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
