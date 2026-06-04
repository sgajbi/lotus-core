# CR-734 External FX Forward Curve Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_external_fx_forward_curve(...)` in the fail-closed external treasury
market-data source-data product support path.

## Finding

External FX forward curve evidence is a downstream DPM supportability boundary, but response
assembly was still embedded in the integration service. Unavailable supportability, missing
treasury source posture, blocked non-claim capabilities, lineage, source-batch fingerprinting,
snapshot identity, and runtime metadata lived directly in the broad integration service.

That kept forward-curve supportability inconsistent with the extracted external currency exposure,
external hedge policy, external eligible hedge instrument, external hedge execution readiness, and
external OMS acknowledgement boundaries.

## Action

Added `external_fx_forward_curve.py` as the focused fail-closed forward-curve response boundary.

The service now delegates response assembly. Focused helper coverage locks unavailable
supportability, missing external FX forward curve source posture, blocked non-claims, empty curve
points, audit echoes, lineage, data-quality status, sorted request fingerprinting, and snapshot
identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_external_fx_forward_curve.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\external_fx_forward_curve.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_fx_forward_curve.py
python -m ruff format --check src\services\query_service\app\services\external_fx_forward_curve.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_fx_forward_curve.py
git diff --check
```
