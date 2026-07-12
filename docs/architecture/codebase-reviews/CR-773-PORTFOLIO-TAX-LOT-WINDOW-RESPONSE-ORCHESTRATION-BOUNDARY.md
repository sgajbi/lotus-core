# CR-773 Portfolio Tax-Lot Window Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_portfolio_tax_lot_window(...)` in the DPM portfolio tax-lot source-data path.

## Finding

Portfolio tax-lot window orchestration still coordinated portfolio existence validation, request
scope binding, buy-state repository paging, page slicing, page-token creation, and response assembly
inline in the broad integration service.

That left the integration service as the owner of tax-lot window workflow policy even though the
portfolio tax-lot module already owned cursor parsing, page-token policy, supportability, lineage,
and response assembly.

## Action

Added `resolve_portfolio_tax_lot_window_response(...)` to `portfolio_tax_lot_window.py`, then routed
`IntegrationService.get_portfolio_tax_lot_window(...)` through that helper with the existing
buy-state repository and page-token codec dependencies.

The service still owns dependency wiring. The portfolio tax-lot module now owns the full source-data
response workflow after dependency injection: portfolio validation, page-token scope validation,
repository paging arguments, page slicing, next-page token creation, and response assembly. Focused
helper coverage locks repository read order, source read arguments, encoded token payload shape,
returned page shape, and missing-portfolio behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\portfolio_tax_lot_window.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py
python -m ruff format --check src\services\query_service\app\services\portfolio_tax_lot_window.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py
git diff --check
```
