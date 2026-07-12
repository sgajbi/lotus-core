# CR-716 Instrument Eligibility Bulk Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_instrument_eligibility_bulk(...)` in the DPM/product-shelf source-data
product support path.

## Finding

Bulk instrument eligibility is a request-order-sensitive read path, but the service method still
assembled row lookup, missing-record fallbacks, supportability, lineage, and runtime metadata inline
after the repository read.

That made product-shelf evidence behavior harder to audit and reuse across DPM readiness checks.

## Action

Added `instrument_eligibility.py` as the focused bulk eligibility response boundary.

The service now reads the requested eligibility rows and delegates response assembly. Focused helper
coverage locks request-order preservation, missing-record fallback behavior, supportability,
data-quality classification, latest evidence timestamp, and lineage.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\instrument_eligibility.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_instrument_eligibility.py
python -m ruff format --check src\services\query_service\app\services\instrument_eligibility.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_instrument_eligibility.py
git diff --check
```
