# CR-758 DPM Source Readiness Fail-Closed Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still repeated local `LookupError` / `ValueError` suppression for
each downstream source read before mapping missing evidence into fail-closed source-family readiness.

That kept DPM fail-closed read semantics duplicated in the broad integration service instead of the
DPM readiness module that owns source-family availability policy.

## Action

Added `dpm_source_read_or_none(...)` to `dpm_source_readiness.py`, then routed mandate, model-target,
eligibility, tax-lot, and market-data source reads through that helper.

The service still owns source call ordering and request arguments, while the DPM readiness module now
owns reusable fail-closed exception handling for unavailable source evidence. Focused helper coverage
locks successful response passthrough and `LookupError` / `ValueError` suppression.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_dpm_source_readiness.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\dpm_source_readiness.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_source_readiness.py
python -m ruff format --check src\services\query_service\app\services\dpm_source_readiness.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_source_readiness.py
git diff --check
```
