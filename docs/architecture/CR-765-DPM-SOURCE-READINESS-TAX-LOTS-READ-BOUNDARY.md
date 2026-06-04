# CR-765 DPM Source Readiness Tax Lots Read Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness orchestration still wrapped the downstream portfolio tax-lot source read inline,
including the fail-closed unavailable-source policy.

That kept tax-lot source read semantics in the broad integration service instead of the DPM
readiness module that owns source-family availability policy and evaluated-universe scope.

## Action

Added `dpm_source_tax_lots_read_or_none(...)` to `dpm_source_readiness.py`, then routed the service
through that helper before resolving the tax-lot source-family outcome.

The service still owns source call ordering and the concrete portfolio tax-lot dependency. The DPM
readiness module now owns reusable tax-lot read scope passthrough and fail-closed unavailable-source
suppression. Focused helper coverage locks portfolio scope passthrough, empty evaluated-universe
passthrough for full-portfolio tax-lot reads, and unavailable-source suppression.

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
