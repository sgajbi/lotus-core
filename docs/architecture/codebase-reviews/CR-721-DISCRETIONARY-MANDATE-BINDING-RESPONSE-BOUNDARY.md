# CR-721 Discretionary Mandate Binding Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_discretionary_mandate_binding(...)` in the DPM source-data product
support path.

## Finding

Discretionary mandate binding is a foundational DPM source-data product used by client
restrictions, sustainability preferences, tax, income, liquidity, model-change, and readiness
flows. The integration service still assembled mandate DTOs, discretionary-authority
supportability, policy-pack completeness, mandate objective/review schedule supportability,
rebalance-band normalization, lineage, and runtime metadata inline beside the repository lookup.

That made the most reused DPM binding policy harder to audit and increased the blast radius of
future source-data product changes.

## Action

Added `discretionary_mandate_binding.py` as the focused mandate binding response boundary.

The service now performs the single binding lookup and delegates response assembly. Focused helper
coverage locks ready, inactive-authority, missing policy-pack, missing objective/review schedule,
overdue review, sparse rebalance-band normalization, policy-pack suppression, lineage, data-quality
normalization, and latest evidence timestamp behavior.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_discretionary_mandate_binding.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\discretionary_mandate_binding.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_discretionary_mandate_binding.py
python -m ruff format --check src\services\query_service\app\services\discretionary_mandate_binding.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_discretionary_mandate_binding.py
git diff --check
```
