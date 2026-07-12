# CR-749 DPM Source Readiness Request Builders

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source readiness orchestration still constructed downstream request DTOs inline for mandate
binding, model targets, instrument eligibility, portfolio tax lots, and market-data coverage.

That kept readiness read-scope policy coupled to the broad integration service instead of the DPM
readiness module that already owns source-family supportability and response assembly.

## Action

Added downstream request builders to `dpm_source_readiness.py` and routed the integration service
through them.

The service still owns sequencing, portfolio context, and fail-closed exception handling, while the
DPM readiness module now owns reusable read-scope construction. Focused helper coverage locks
mandate policy-pack inclusion, active model-target reads, eligibility rationale suppression,
tax-lot full-portfolio fallback, market-data coverage scope, staleness policy, valuation currency,
and tenant propagation.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter operator commands, migration policy, or published
database runbooks.

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
