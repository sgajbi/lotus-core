# CR-738 Risk-Free Series Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_risk_free_series(...)` in the market/reference source-data product path.

## Finding

Risk-free series response assembly was still embedded in the broad integration service.
Deterministic request fingerprinting, resolved-window mapping, risk-free point DTO mapping,
lineage, market-reference data-quality classification, latest evidence timestamp selection, and
runtime metadata lived beside currency normalization and the repository read.

That made risk-free market-reference evidence less auditable and kept mapping policy coupled to
orchestration.

## Action

Added `risk_free_series.py` as the focused risk-free series response boundary.

The service now normalizes currency, reads risk-free rows, and delegates response assembly. Focused
helper coverage locks fingerprint generation, resolved-window mapping, point mapping, lineage,
complete data-quality classification, and latest evidence timestamp selection.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_risk_free_series.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\risk_free_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_series.py
python -m ruff format --check src\services\query_service\app\services\risk_free_series.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_risk_free_series.py
git diff --check
```
