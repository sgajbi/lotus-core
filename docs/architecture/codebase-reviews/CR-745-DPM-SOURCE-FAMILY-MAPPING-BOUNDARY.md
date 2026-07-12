# CR-745 DPM Source Family Mapping Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_dpm_source_readiness(...)` in the DPM source-readiness path.

## Finding

DPM source readiness orchestration still repeated family-readiness DTO mapping for mandate,
model-target, eligibility, tax-lot, and market-data source products inline in the broad integration
service.

That kept source-family vocabulary, product names, missing/stale item mapping, and evidence-count
policy coupled to repository orchestration.

## Action

Added focused source-family mapping helpers to `dpm_source_readiness.py` and routed the integration
service through them.

The service still owns sequential source reads and fail-closed exception handling, while the DPM
readiness policy module now owns reusable family DTO mapping and evaluated-instrument scope
deduplication. Focused helper coverage locks family names, product names, missing/stale scope
composition, evidence counts, and deterministic instrument-scope sorting.

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
