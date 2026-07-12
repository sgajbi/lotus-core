# CR-534: Reprocessing Key Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reprocessing-key count and list queries.

## Finding

`OperationsRepository.get_reprocessing_keys_count(...)` and
`OperationsRepository.get_reprocessing_keys(...)` both maintained the same support scope:

1. portfolio ownership,
2. as-of support evidence guard,
3. governed stored reprocessing status predicate,
4. normalized security identifier predicate,
5. watermark date predicate.

Duplicating that scope made valuation reprocessing pagination vulnerable to future count/list drift
when adding or correcting operational filters.

## Change

1. Added `_apply_reprocessing_key_scope(...)` as the shared position-state reprocessing-key filter
   helper.
2. Reused that helper from both reprocessing-key count and list queries.
3. Preserved existing invalid-security short-circuit behavior, direct stored-status comparisons,
   normalized security predicate, stale-priority ordering, offset/limit semantics, and response
   shape.

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
is a maintainability hardening slice that keeps valuation reprocessing key pagination aligned to
one governed filter scope.
