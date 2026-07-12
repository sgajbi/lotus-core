# CR-769 Portfolio Tax-Lot Page Token Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_portfolio_tax_lot_window(...)` in the DPM portfolio tax-lot source-data path.

## Finding

Portfolio tax-lot orchestration still converted next-page token payloads into encoded page tokens
inline after the request-scope helper had already resolved cursor identity and token scope policy.

That kept terminal/non-terminal token encoding behavior in the broad integration service instead of
the portfolio tax-lot module that owns tax-lot paging semantics.

## Action

Added `portfolio_tax_lot_page_token(...)` to `portfolio_tax_lot_window.py`, then routed the service
through that helper with the existing service encoder dependency.

The service still owns portfolio existence validation, buy-state repository reads, and token encoder
implementation. The portfolio tax-lot module now owns reusable next-page payload suppression and
encoded-token passthrough. Focused helper coverage locks encoded payload passthrough and
terminal-page no-op encoding.

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
