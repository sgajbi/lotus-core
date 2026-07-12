# CR-723 Sustainability Preference Profile Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_sustainability_preference_profile(...)` in the DPM/client source-data
product support path.

## Finding

Sustainability preference profile resolution is a client-governance input for DPM construction, but
response assembly was still embedded in the integration service. Preference DTO mapping,
empty-profile supportability, lineage, source-batch fingerprinting, snapshot identity, and runtime
metadata lived beside mandate binding resolution and preference repository reads.

That made sustainability-aware construction policy harder to audit and kept the client profile
source-data family inconsistent with the newly extracted restriction profile boundary.

## Action

Added `sustainability_preference_profile.py` as the focused sustainability preference response
boundary.

The service now resolves the mandate binding, reads effective preference rows, and delegates
response assembly. Focused helper coverage locks ready and empty-profile supportability,
preference mapping, latest evidence timestamp selection across binding and preference evidence,
lineage, data-quality status, source-batch fingerprinting, and snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_sustainability_preference_profile.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\sustainability_preference_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_sustainability_preference_profile.py
python -m ruff format --check src\services\query_service\app\services\sustainability_preference_profile.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_sustainability_preference_profile.py
git diff --check
```
