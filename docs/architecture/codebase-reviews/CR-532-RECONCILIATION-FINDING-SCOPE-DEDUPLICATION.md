# CR-532: Reconciliation Finding Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository reconciliation-finding count and list queries.

## Finding

`OperationsRepository.get_reconciliation_findings(...)` and
`OperationsRepository.get_reconciliation_findings_count(...)` both maintained the same support
scope:

1. reconciliation run id,
2. as-of support evidence guard,
3. finding id,
4. normalized security id,
5. transaction id.

Duplicating that scope made reconciliation-finding pagination easier to drift, especially around
the normalized security-id expression that needs to stay aligned between count and list queries.

## Change

1. Added `_apply_reconciliation_finding_scope(...)` as the shared reconciliation-finding filter
   helper.
2. Reused that helper from both finding count and list queries.
3. Preserved invalid security-id short-circuit behavior, severity ordering, limit semantics, and
   direct stored severity/status predicates.

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
is a maintainability hardening slice that keeps reconciliation-finding support pagination aligned to
one governed filter scope.
