# CR-545: Reprocessing Health Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reprocessing health summary read.

## Finding

`OperationsRepository.get_reprocessing_health_summary(...)` manually applied the same
position-state portfolio and as-of scope already centralized for reprocessing key count/list reads.
That kept the support overview reprocessing health summary exposed to predicate drift from the
paged reprocessing key investigation surface.

The aggregate intentionally needs all position-state statuses in its base scope because the
`REPROCESSING` filters are part of the aggregate metrics, so only the shared portfolio/as-of scope
should be applied.

## Change

1. Reused `_apply_reprocessing_key_scope(...)` for the reprocessing health base query.
2. Left status and stale-window predicates in the aggregate expressions so active and stale key
   metrics preserve existing semantics.
3. Preserved selected columns, oldest-key ordering, as-of behavior, normalized security output, and
   response shape.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
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
is a maintainability hardening slice that keeps support overview reprocessing health aligned with
the governed reprocessing key support scope.
