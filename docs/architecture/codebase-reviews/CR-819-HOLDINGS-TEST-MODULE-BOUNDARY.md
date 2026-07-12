# CR-819 Holdings Test Module Boundary

## Status

Hardened on 2026-06-01.

## Scope

`tests/unit/services/query_service/services/test_position_service.py` and focused HoldingsAsOf
policy helper tests.

## Finding

After the HoldingsAsOf policy extractions, helper-policy tests were still accumulating inside
`test_position_service.py`. That made the service test module carry both service orchestration
coverage and direct HoldingsAsOf policy coverage, weakening the source/test ownership boundary and
making future helper additions harder to scan.

## Action

Created `test_position_holdings.py` as the dedicated HoldingsAsOf helper-policy test module and
moved the effective as-of scope tests there. This keeps the recent HoldingsAsOf request-scope
policy pinned directly to `position_holdings.py` while preserving existing service-orchestration
coverage.

This is the first incremental split of the broader position-service helper test cluster; future
slices can continue moving the remaining direct holdings helper tests out of the service test file.

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
