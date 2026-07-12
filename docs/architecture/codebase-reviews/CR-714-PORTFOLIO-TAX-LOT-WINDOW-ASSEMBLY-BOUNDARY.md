# CR-714 Portfolio Tax-Lot Window Assembly Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_portfolio_tax_lot_window(...)` in the DPM/source-data product support path.

## Finding

The portfolio tax-lot window endpoint mixed repository orchestration with cursor parsing,
tax-lot DTO assembly, requested-security coverage, supportability classification, page metadata,
lineage, and runtime metadata.

That path is a real DPM/rebalancing support hot path. Keeping page and supportability policy inline
with repository reads made it harder to audit missing-security semantics, partial-page behavior, and
evidence timestamps for bank-facing tax-lot source data.

## Action

Added `portfolio_tax_lot_window.py` as the focused portfolio tax-lot assembly boundary.

The service now:

1. validates portfolio existence,
2. validates cursor scope,
3. delegates cursor sort-key parsing,
4. reads one page plus sentinel row from the buy-state repository,
5. encodes the next cursor,
6. delegates tax-lot DTO assembly, supportability, page metadata, lineage, and runtime metadata.

Focused helper coverage locks:

1. cursor sort-key parsing,
2. partial-page supportability,
3. requested-security missing coverage,
4. empty-portfolio unavailable state,
5. latest-evidence timestamp and lineage.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

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
