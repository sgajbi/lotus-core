# CR-732 External Hedge Policy Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_external_hedge_policy(...)` in the fail-closed external treasury source-data
product support path.

## Finding

External hedge policy evidence is a downstream DPM supportability boundary, but response assembly
was still embedded in the integration service. Unavailable supportability, missing treasury source
families, blocked non-claim capabilities, lineage, source-batch fingerprinting, snapshot identity,
and runtime metadata lived beside mandate binding resolution.

That kept the external treasury fail-closed family inconsistent with the extracted external
currency exposure, external hedge execution readiness, and external OMS acknowledgement boundaries.

## Action

Added `external_hedge_policy.py` as the focused fail-closed hedge policy response boundary.

The service now resolves the mandate binding and delegates response assembly. Focused helper
coverage locks unavailable supportability, missing external hedge policy source posture, blocked
non-claims, empty policy rules, lineage, data-quality status, sorted request fingerprinting, and
snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_external_hedge_policy.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\external_hedge_policy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_hedge_policy.py
python -m ruff format --check src\services\query_service\app\services\external_hedge_policy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_hedge_policy.py
git diff --check
```
