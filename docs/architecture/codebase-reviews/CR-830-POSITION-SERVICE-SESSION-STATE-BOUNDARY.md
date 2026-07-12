# CR-830 Position Service Session State Boundary

## Status

Hardened on 2026-06-02.

## Scope

`src/services/query_service/app/services/position_service.py` and
`tests/unit/services/query_service/services/test_position_service.py`.

## Finding

After the position-history and HoldingsAsOf orchestration helpers were extracted, `PositionService`
still retained the raw `AsyncSession` on `self.db` even though the service only uses the
constructed `PositionRepository`.

Keeping unused service state makes the service object harder to reason about and can invite future
callers to bypass the repository boundary.

## Action

Removed the unused `self.db` assignment from `PositionService.__init__(...)`. Added focused
coverage proving the service still constructs `PositionRepository` from the supplied session while
not retaining the raw session as public service state.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service-state cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings_response.py tests\unit\services\query_service\services\test_position_history_reads.py tests\unit\services\query_service\services\test_portfolio_validation.py tests\unit\services\query_service\services\test_position_holdings_reads.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_history.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\position_service.py tests\unit\services\query_service\services\test_position_service.py
python -m ruff format --check src\services\query_service\app\services\position_service.py tests\unit\services\query_service\services\test_position_service.py
git diff --check
```
