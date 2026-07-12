# CR-740 Classification Taxonomy Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_classification_taxonomy(...)` in the market/reference source-data product
path.

## Finding

Classification taxonomy response assembly was still embedded in the broad integration service.
Deterministic request fingerprinting, taxonomy entry DTO mapping, market-reference data-quality
classification, latest evidence timestamp selection, and runtime metadata lived beside the
repository read.

That kept taxonomy mapping and source-data metadata policy coupled to orchestration.

## Action

Added `classification_taxonomy.py` as the focused classification taxonomy response boundary.

The service now reads taxonomy rows and delegates response assembly. Focused helper coverage locks
fingerprint generation, taxonomy entry mapping, complete data-quality classification, and latest
evidence timestamp selection.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_classification_taxonomy.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\classification_taxonomy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_classification_taxonomy.py
python -m ruff format --check src\services\query_service\app\services\classification_taxonomy.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_classification_taxonomy.py
git diff --check
```
