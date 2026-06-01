# CR-712 Benchmark Composition Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_benchmark_composition_window(...)` in the query service source-data product path.

## Finding

The benchmark composition endpoint mixed repository orchestration with pure response policy inside
the large integration service class. Definition currency validation, latest-effective definition
selection, component window resolution, lineage, and source-data product runtime metadata all lived
inline with repository calls.

That shape made a bank-facing benchmark evidence product harder to audit because the service method
hid the actual contract policy inside orchestration code.

## Action

Added `benchmark_composition.py` as the focused benchmark composition assembly boundary.

The service now:

1. reads overlapping benchmark definitions,
2. delegates definition validation and latest-effective selection,
3. reads overlapping component rows only after the definition context is valid,
4. delegates segment resolution, lineage, and runtime metadata assembly.

Focused helper coverage locks:

1. missing definition behavior,
2. intra-window benchmark-currency drift rejection,
3. superseded component segment resolution,
4. data-quality metadata,
5. lineage.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal source-data product
assembly boundary and does not alter operator commands, migration policy, or published database
runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_benchmark_composition.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
ruff check src\services\query_service\app\services\benchmark_composition.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_composition.py
ruff format --check src\services\query_service\app\services\benchmark_composition.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_benchmark_composition.py
git diff --check
```
