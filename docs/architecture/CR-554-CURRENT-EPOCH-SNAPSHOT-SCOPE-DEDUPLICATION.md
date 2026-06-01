# CR-554: Current Epoch Snapshot Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository current-epoch snapshot evidence reads.

## Finding

`OperationsRepository.get_snapshot_valuation_coverage_summary(...)` repeated the same
daily-position-snapshot to position-state current-epoch join, portfolio predicate, optional snapshot
date predicate, and dual snapshot/state timestamp fence used by current-epoch snapshot date reads.
That kept valuation coverage evidence exposed to drift from the latest/booked snapshot-date support
queries.

The affected reads intentionally share the current-epoch snapshot scope while differing in selected
columns and aggregate behavior.

## Change

1. Added `_apply_current_epoch_snapshot_scope(...)` to centralize the current-epoch snapshot join,
   portfolio predicate, optional exact or upper-bound business-date predicate, and timestamp fence.
2. Reused it from `_current_epoch_snapshot_date_stmt(...)`.
3. Reused it from `get_snapshot_valuation_coverage_summary(...)`.
4. Preserved valuation coverage aggregate definitions, raw `UNVALUED` predicate semantics, scalar
   execution shape, and response type.

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
is a maintainability hardening slice that keeps current-epoch snapshot valuation coverage and
snapshot-date evidence aligned to one governed query scope.
