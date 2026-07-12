# CR-547: Position State Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository position-state detail read.

## Finding

`OperationsRepository.get_position_state(...)` manually applied the same position-state portfolio,
normalized security, and as-of scope already centralized for reprocessing key support reads. That
kept the direct position-state detail query exposed to predicate drift from the paged
reprocessing-key and lineage investigation surfaces.

The detail read intentionally needs only portfolio, normalized security, and as-of filtering. It
must not inherit reprocessing status or watermark predicates.

## Change

1. Reused `_apply_reprocessing_key_scope(...)` for the position-state detail query.
2. Passed only `portfolio_id`, `normalized_security_id`, and `as_of`.
3. Preserved invalid-security short-circuit behavior, scalar execution shape, and response type.

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
is a maintainability hardening slice that keeps direct position-state support reads aligned with
the governed position-state scope used by reprocessing support evidence.
