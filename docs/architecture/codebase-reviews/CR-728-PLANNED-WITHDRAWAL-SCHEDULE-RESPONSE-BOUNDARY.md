# CR-728 Planned Withdrawal Schedule Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_planned_withdrawal_schedule(...)` in the DPM/client source-data product
support path.

## Finding

Planned withdrawal schedules are private-banking cash movement evidence used by downstream DPM
support flows, but response assembly was still embedded in the integration service. Withdrawal DTO
mapping, empty withdrawal supportability, horizon-specific fingerprinting, lineage, snapshot
identity, and runtime metadata lived beside mandate binding resolution and withdrawal repository
reads.

That made withdrawal evidence harder to audit and left the income, reserve, and withdrawal
source-data family uneven after the adjacent response boundaries were extracted.

## Action

Added `planned_withdrawal_schedule.py` as the focused planned withdrawal response boundary.

The service now resolves the mandate binding, reads horizon-bounded planned withdrawal rows, and
delegates response assembly. Focused helper coverage locks ready and empty-withdrawal
supportability, withdrawal mapping, latest evidence timestamp selection across binding and
withdrawal evidence, lineage, data-quality status, horizon-aware source-batch fingerprinting, and
snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_planned_withdrawal_schedule.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\planned_withdrawal_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_planned_withdrawal_schedule.py
python -m ruff format --check src\services\query_service\app\services\planned_withdrawal_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_planned_withdrawal_schedule.py
git diff --check
```
