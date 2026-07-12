# CR-787 Portfolio Manager Book Membership Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_portfolio_manager_book_membership(...)` in the portfolio-manager book
source-data product path.

## Finding

Portfolio manager book membership orchestration still coordinated portfolio-type normalization,
portfolio repository reads, and response assembly inline in the broad integration service.

That left the integration service as the owner of PM book membership workflow policy even though
the portfolio manager book membership module already owned portfolio-type scope normalization,
member mapping, supportability, lineage, snapshot identity, and runtime metadata.

## Action

Added `resolve_portfolio_manager_book_membership_response(...)` to
`portfolio_manager_book_membership.py`, then routed
`IntegrationService.resolve_portfolio_manager_book_membership(...)` through that helper with the
existing portfolio repository dependency.

The service still owns dependency wiring. The portfolio manager book membership module now owns the
full source-data response workflow after dependency injection: portfolio-type normalization,
repository read arguments, and response assembly. Focused helper coverage locks repository read
arguments and normalized portfolio-type scope.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_portfolio_manager_book_membership.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\portfolio_manager_book_membership.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_portfolio_manager_book_membership.py
python -m ruff format --check src\services\query_service\app\services\portfolio_manager_book_membership.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_portfolio_manager_book_membership.py
git diff --check
```
