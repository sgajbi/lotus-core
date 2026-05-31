# CR-531: Reconciliation Run Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reconciliation-run count and list queries.

## Finding

`OperationsRepository.get_reconciliation_runs_count(...)` and
`OperationsRepository.get_reconciliation_runs(...)` both maintained the same reconciliation-run
support scope:

1. portfolio ownership,
2. as-of support evidence guard,
3. run id,
4. correlation id,
5. requester,
6. dedupe key,
7. reconciliation type,
8. governed stored status predicate.

Duplicating that predicate chain meant support pagination could drift if a future operational
filter was added to the list query but missed in the count query, or the reverse.

## Change

1. Added `_apply_reconciliation_run_scope(...)` as the shared reconciliation-run support scope.
2. Reused that helper from both count and list queries.
3. Preserved existing direct stored-status comparisons, ordering, offset/limit semantics, and
   response shape.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
4. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Touched-surface ruff passed.
3. Touched-surface format check passed.
4. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability hardening slice that keeps reconciliation-run support pagination aligned to one
governed filter scope.
