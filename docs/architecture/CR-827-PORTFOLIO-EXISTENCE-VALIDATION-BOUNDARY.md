# CR-827 Portfolio Existence Validation Boundary

## Status

Hardened on 2026-06-01.

## Scope

`src/services/query_service/app/services/portfolio_validation.py`,
`src/services/query_service/app/services/position_service.py`, and
`tests/unit/services/query_service/services/test_portfolio_validation.py`.

## Finding

`PositionService` duplicated the same portfolio existence check in both position history and
HoldingsAsOf reads. Each path called `portfolio_exists(...)` and raised the same `LookupError`
message when the portfolio was missing.

That kept reusable validation behavior embedded in endpoint-specific service methods and made it
harder to standardize portfolio existence validation across query-service modules over time.

## Action

Created `ensure_portfolio_exists(...)` in `portfolio_validation.py` and routed the two
`PositionService` portfolio existence checks through it. Added direct tests for the known-portfolio
and missing-portfolio `LookupError` behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal validation-boundary
cleanup and does not alter API shape, operator commands, migration policy, or published database
runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\portfolio_validation.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
python -m ruff format --check src\services\query_service\app\services\position_service.py src\services\query_service\app\services\portfolio_validation.py tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py
git diff --check
```
