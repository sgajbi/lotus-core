# CR-750 DPM Fail-Closed Family Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source readiness orchestration still constructed fail-closed source-family responses inline for
missing mandate binding, missing model portfolio identity, unavailable model targets, unavailable
instrument eligibility, empty instrument universe, unavailable tax lots, and unavailable market
data.

That kept DPM readiness reason-code vocabulary and missing-item policy coupled to the broad
integration service instead of the DPM readiness module that owns source-family supportability.

## Action

Added fail-closed source-family helper constructors to `dpm_source_readiness.py` and routed the
integration service through them.

The service still owns call sequencing and exception handling, while the DPM readiness module now
owns reusable unavailable-family policy. Focused helper coverage locks family names, product names,
reason codes, missing-item payloads, and the capped eligibility missing-item sample.

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
