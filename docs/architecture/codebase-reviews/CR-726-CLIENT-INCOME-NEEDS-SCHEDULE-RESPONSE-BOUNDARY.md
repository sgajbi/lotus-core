# CR-726 Client Income Needs Schedule Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_client_income_needs_schedule(...)` in the DPM/client source-data product
support path.

## Finding

Client income-needs schedule resolution is a private-banking cashflow and suitability input, but
response assembly was still embedded in the integration service. Schedule DTO mapping, empty
schedule supportability, lineage, source-batch fingerprinting, snapshot identity, and runtime
metadata lived beside mandate binding resolution and income-needs repository reads.

That made income-needs evidence harder to audit and kept the client source-data family inconsistent
with the extracted restriction, sustainability, and tax boundaries.

## Action

Added `client_income_needs_schedule.py` as the focused income-needs schedule response boundary.

The service now resolves the mandate binding, reads effective income-needs rows, and delegates
response assembly. Focused helper coverage locks ready and empty-schedule supportability, schedule
mapping, latest evidence timestamp selection across binding and schedule evidence, lineage,
data-quality status, source-batch fingerprinting, and snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_client_income_needs_schedule.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\client_income_needs_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_income_needs_schedule.py
python -m ruff format --check src\services\query_service\app\services\client_income_needs_schedule.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_client_income_needs_schedule.py
git diff --check
```
