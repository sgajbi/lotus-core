# CR-544: Reprocessing Scope Model Boundary

Date: 2026-05-31

## Scope

Query-service operations support repository model boundary.

## Finding

After CR-543 moved operations support summary models out of `operations_repository.py`, the
repository still carried `ResetWatermarkReprocessingJobScope` as a local dataclass. That type is a
small immutable scope carrier used by the reprocessing job count/list query family, not repository
behavior.

Leaving it in the SQL repository module kept one remaining model definition mixed into the
monolithic repository and weakened the new model boundary.

## Change

1. Moved `ResetWatermarkReprocessingJobScope` into `operations_models.py`.
2. Reused the extracted scope carrier from `operations_repository.py`.
3. Preserved the reset-watermarks reprocessing job query shape, correlated portfolio-scope
   predicate, payload security/date expressions, and response behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/repositories/operations_models.py tests/unit/services/query_service/repositories/test_operations_repository.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/repositories/operations_models.py tests/unit/services/query_service/repositories/test_operations_repository.py`
6. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Alembic reported a single current head.
3. Migration SQL contract smoke passed.
4. Touched-surface ruff passed.
5. Touched-surface format check passed.
6. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a small modularity hardening slice that completes the operations repository data-carrier
extraction started in CR-543.
