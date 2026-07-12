# CR-539: Lineage Key Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository lineage-key count and list queries.

## Finding

`OperationsRepository.get_lineage_keys_count(...)` and
`OperationsRepository.get_lineage_keys(...)` maintained their own position-state support scope:

1. portfolio ownership,
2. as-of support evidence guard,
3. governed stored reprocessing status predicate,
4. normalized security identifier predicate.

That scope matched the position-state reprocessing-key scope already centralized for valuation
reprocessing support, but lineage count/list still applied it manually. Duplicating the same
position-state predicate set made lineage pagination vulnerable to drift from reprocessing-key
support behavior.

## Change

1. Reused `_apply_reprocessing_key_scope(...)` from lineage-key count and list queries.
2. Preserved existing invalid-security short-circuit behavior, direct stored-status comparisons,
   normalized security predicate, lineage scalar projections, artifact-gap ordering, offset/limit
   semantics, and response shape.

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
is a maintainability hardening slice that keeps lineage and valuation reprocessing support reads
aligned to one governed position-state filter scope.
