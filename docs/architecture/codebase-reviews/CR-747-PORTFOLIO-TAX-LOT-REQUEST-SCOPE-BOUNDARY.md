# CR-747 Portfolio Tax-Lot Request Scope Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_portfolio_tax_lot_window(...)` in the DPM portfolio tax-lot source-data
product path.

## Finding

Portfolio tax-lot request fingerprinting, cursor extraction, page token scope validation, and
next-page token payload construction were still embedded in the broad integration service.

That kept deterministic paging identity policy coupled to buy-state repository orchestration,
despite tax-lot response and supportability policy already being helper-owned.

## Action

Added portfolio tax-lot request-scope and next-page token payload helpers to
`portfolio_tax_lot_window.py`.

The service now decodes the opaque page token, delegates request-scope validation and cursor
mapping, then uses the resulting scope for repository reads and token encoding. Focused helper
coverage locks filter fingerprinting, cursor binding, token mismatch rejection, and last-lot
next-page payload shape.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter operator commands, migration policy, or published
database runbooks.

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
