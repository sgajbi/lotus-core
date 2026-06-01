# CR-744 Risk-Free Coverage Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_risk_free_coverage(...)` in the market/reference source-data product path.

## Finding

Risk-free coverage response assembly still built the normalized-currency request fingerprint inline
in the broad integration service before invoking the shared market-reference coverage mapper.

That kept risk-free coverage identity policy coupled to orchestration instead of making the
coverage response boundary reusable and directly testable.

## Action

Added `risk_free_coverage.py` as the focused risk-free coverage response boundary.

The service still owns currency normalization before repository lookup, then delegates
normalized-currency response assembly. Focused helper coverage locks currency-scoped
fingerprinting, source-data runtime metadata, complete coverage classification, and quality
distribution mapping.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_risk_free_coverage.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\risk_free_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_coverage.py
python -m ruff format --check src\services\query_service\app\services\risk_free_coverage.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_coverage.py
git diff --check
```
