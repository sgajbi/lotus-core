# CR-786 DPM Source Readiness Reader Wiring Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source-readiness response orchestration had already moved into `dpm_source_readiness.py`, but
the public integration-service method still contained the full reader-wiring construction,
including the tax-lot adapter lambda that translates the reader contract into the existing service
method signature.

That left dependency composition mixed into the public endpoint-facing method and made the
source-readiness entry point longer than the surrounding delegated methods.

## Action

Extracted the DPM source-readiness reader composition into
`IntegrationService._dpm_source_readiness_readers(...)`.

The public method now only passes portfolio scope, request scope, and the composed reader contract
to `resolve_dpm_source_readiness_response(...)`. The private helper owns the service-method wiring
for mandate binding, model targets, instrument eligibility, portfolio tax lots, and market-data
coverage while preserving the existing tax-lot adapter behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal dependency-wiring
boundary and does not alter API shape, operator commands, migration policy, or published database
runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_dpm_source_readiness.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_source_readiness.py
python -m ruff format --check src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_source_readiness.py
git diff --check
```
