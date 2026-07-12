# CR-821 Holdings Response Mapping Test Boundary

## Status

Hardened on 2026-06-01.

## Scope

`tests/unit/services/query_service/services/test_position_service.py` and
`tests/unit/services/query_service/services/test_position_holdings.py`.

## Finding

After CR-820 moved the first HoldingsAsOf helper-policy tests into the dedicated holdings test
module, response metadata, valuation mapping, public position DTO assembly, row assembly, and
weight assignment tests still lived in `test_position_service.py`.

Those tests directly exercise `position_holdings.py` helper behavior and do not require
`PositionService` orchestration or repository mocks. Keeping them in the service test file made the
service test boundary noisier and obscured which tests prove reusable holdings policy.

## Action

Moved the response metadata, valuation mapping, position response mapping, portfolio row assembly,
weight assignment, and weight base value helper tests into `test_position_holdings.py`.
`test_position_service.py` is now further reduced toward service orchestration coverage while the
holdings helper module owns its own direct policy proof.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal test-ownership cleanup
and does not alter API shape, operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings.py
python -m ruff format --check tests\unit\services\query_service\services\test_position_service.py tests\unit\services\query_service\services\test_position_holdings.py
git diff --check
```
