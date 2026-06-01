# CR-719 CIO Model Change Cohort Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_cio_model_change_affected_cohort(...)` in the DPM source-data product
support path.

## Finding

CIO model-change affected-cohort resolution is a core DPM source-data product for rollout and
rebalancing workflows, but response assembly was still embedded in the integration service.
Affected mandate mapping, supportability, deterministic event and snapshot identity, lineage, and
runtime metadata lived beside definition resolution and mandate repository reads.

That shape made model-change cohort evidence harder to audit, reuse, and test independently from
request orchestration.

## Action

Added `cio_model_change_cohort.py` as the focused CIO model-change cohort response boundary.

The service now resolves the approved model definition, reads affected mandate rows, and delegates
response assembly. Focused helper coverage locks ready and empty-cohort supportability,
filters-applied semantics, deterministic event/snapshot identity, source-batch fingerprint,
lineage fallback behavior, latest evidence timestamp selection, and data-quality status.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_cio_model_change_cohort.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\cio_model_change_cohort.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_cio_model_change_cohort.py
python -m ruff format --check src\services\query_service\app\services\cio_model_change_cohort.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_cio_model_change_cohort.py
git diff --check
```
