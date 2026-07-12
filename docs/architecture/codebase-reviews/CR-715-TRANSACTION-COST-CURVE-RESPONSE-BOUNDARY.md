# CR-715 Transaction Cost Curve Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_transaction_cost_curve(...)` and `transaction_cost_curve.py` in the
transaction-cost evidence source-data product path.

## Finding

Transaction cost curve point and page construction already lived in a focused helper, but the final
response policy still remained in the large integration service method. Missing requested-security
coverage, partial-page supportability, page metadata, lineage, and runtime metadata were separated
from the curve-page evidence model they describe.

That made a calculation-support product harder to audit because curve eligibility and response
supportability were split across modules.

## Action

Added `build_transaction_cost_curve_response(...)` to the existing transaction-cost curve helper.

The service now:

1. validates portfolio existence and page-token scope,
2. reads transaction-cost evidence,
3. delegates curve-page construction,
4. encodes the next cursor,
5. delegates final response assembly, supportability, lineage, and runtime metadata.

Focused helper coverage locks:

1. partial-page supportability,
2. missing requested-security coverage,
3. next-page metadata,
4. latest-evidence timestamp,
5. lineage.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_transaction_cost_curve.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\transaction_cost_curve.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_transaction_cost_curve.py
python -m ruff format --check src\services\query_service\app\services\transaction_cost_curve.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_transaction_cost_curve.py
git diff --check
```
