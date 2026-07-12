# CR-718 Portfolio Manager Book Membership Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_portfolio_manager_book_membership(...)` in the DPM source-data product
support path.

## Finding

Portfolio-manager book membership is a core DPM source-data product for source-owned cohort
discovery, but response assembly was still embedded in the integration service. Portfolio-type
scope normalization, member DTO mapping, supportability, deterministic snapshot identity, lineage,
and runtime metadata lived beside repository orchestration.

That shape made PM-book evidence policy harder to audit and reuse from DPM readiness and
source-data product flows.

## Action

Added `portfolio_manager_book_membership.py` as the focused PM-book response boundary.

The service now normalizes the portfolio-type read scope, reads membership rows from the portfolio
repository, and delegates response assembly. Focused helper coverage locks portfolio-type
normalization, ready and empty-book supportability, filters-applied semantics, latest evidence
timestamp selection, snapshot identity, lineage, and data-quality status.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

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
