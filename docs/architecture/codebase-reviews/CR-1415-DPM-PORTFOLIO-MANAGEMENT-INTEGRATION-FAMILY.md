# CR-1415 DPM Portfolio Management Integration Family

## Status

Fixed-local candidate on 2026-07-06.

## Scope

Remaining `IntegrationService` DPM portfolio-management source-data products in `query_service`.

## Finding

GitHub issue #548 remained valid after the earlier family extractions because
`IntegrationService` still directly imported and invoked portfolio-manager book membership, CIO
model-change affected cohort, and DPM portfolio-universe resolver modules. Those methods shared the
same DPM portfolio-management source-data lens but still coupled portfolio repository access,
reference repository access, and DPM universe page-token wiring to the broad facade.

## Action

Added `DpmPortfolioManagementIntegrationService` as the final DPM portfolio-management
contract-family boundary. The family service owns reference-repository provider access,
portfolio-repository provider access, and DPM portfolio-universe page-token adapter wiring while
delegating to the existing resolver modules.

`IntegrationService` now constructs the family service from its existing dependency bundle and keeps
the public facade methods as thin compatibility delegates.

## Compatibility

No downstream API contract changes are intended in this slice. Existing route handlers and service
callers continue to use the same facade methods and DTO contracts. Portfolio-manager membership
filters, CIO model-change cohort behavior, DPM portfolio-universe paging, page-token scope
validation, supportability, lineage, source-data product names, repository SQL, database schema, and
runtime topology are unchanged.

## Issue Closure Impact

This slice completes the #548 local implementation path when combined with CR-1410 through CR-1414:
the broad facade remains available for router compatibility, while the implementation is split into
contract-family services with narrow repository and DTO imports.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_service.py -q
python -m ruff check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\dpm_portfolio_management_integration_service.py tests\unit\services\query_service\services\test_integration_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\dpm_portfolio_management_integration_service.py tests\unit\services\query_service\services\test_integration_service.py
python -m mypy src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\dpm_portfolio_management_integration_service.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```

## Current Ownership

CR-1539 separated portfolio-manager books by their portfolio-master source. CR-1540 moved CIO
affected cohorts and DPM universe candidates into the layered `dpm_portfolio_population`
capability. `DpmPortfolioManagementIntegrationService` is retired.
