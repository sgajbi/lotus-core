# CR-829 Holdings Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`src/services/query_service/app/services/position_service.py`,
`src/services/query_service/app/services/position_holdings_response.py`, and
`tests/unit/services/query_service/services/test_position_holdings_response.py`.

## Finding

After the HoldingsAsOf read-scope helpers were extracted, `PositionService.get_portfolio_positions(...)`
still coordinated the remaining HoldingsAsOf response assembly inline: source-row reads, snapshot
and history merge, fallback valuation lookup, position DTO assembly, weight assignment,
held-since support evidence, data-quality classification, and source-data-product response
metadata.

That kept a large workflow in the endpoint service even though each step had reusable helper
coverage.

## Action

Created `position_holdings_response.py` with `portfolio_holdings_response(...)`. The helper owns
the HoldingsAsOf response orchestration and composes the existing holdings policy/read helpers.
`PositionService.get_portfolio_positions(...)` now validates portfolio existence, resolves the
effective read date, and delegates response assembly to the helper. Added direct coverage for a
snapshot-backed HoldingsAsOf response including held-since evidence, market-price freshness scope,
weight assignment, data-quality status, and latest evidence timestamp.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service-boundary cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_response.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_holdings_response.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_response.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
python -m ruff format --check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\position_holdings_response.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_response.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
git diff --check
```
