# CR-810 Position Fallback Valuation Scope Boundary

## Status

Hardened on 2026-06-01.

## Scope

`PositionService.get_portfolio_positions(...)` in the query-service holdings read path.

## Finding

The portfolio positions read path still decided inline when to fetch latest snapshot valuation
fallback data and which history-only security identifiers should scope that lookup. That policy is
domain-significant because it preserves valuation continuity for history-supplemented holdings
without over-broadening the fallback query when snapshot rows are authoritative.

Keeping the lookup decision and security-scope normalization inline made valuation fallback
behavior harder to review and less directly testable.

## Action

Extracted `should_fetch_fallback_valuation_map(...)` and
`fallback_valuation_security_ids(...)` in `position_service.py`, then routed
`PositionService.get_portfolio_positions(...)` through those helpers.

Focused coverage now locks empty-scope no-fetch behavior, snapshot-authoritative no-fetch
behavior, history-only fetch behavior, history-supplement fetch behavior, normalized security
identity, duplicate elimination, sorting, and blank security filtering.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py tests\unit\services\query_service\services\test_position_service.py
python -m ruff format --check src\services\query_service\app\services\position_service.py tests\unit\services\query_service\services\test_position_service.py
git diff --check
```
