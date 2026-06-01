# CR-555: Mismatch Snapshot Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository position-history versus snapshot mismatch count.

## Finding

`OperationsRepository.get_position_snapshot_history_mismatch_count(...)` still built its
latest-snapshot subquery with a local daily-position-snapshot to position-state current-epoch join,
portfolio predicate, and dual timestamp fence after current-epoch snapshot reads were centralized.
That left mismatch evidence exposed to drift from snapshot-date and valuation-coverage evidence.

The mismatch query intentionally keeps its position-history side separate, because that side joins
`PositionHistory` to `PositionState` and aggregates history-specific dates.

## Change

1. Reused `_apply_current_epoch_snapshot_scope(...)` for the latest-snapshot side of the mismatch
   query.
2. Preserved selected snapshot columns, grouping, outer-join shape, timestamp fence, and mismatch
   count semantics.
3. Left the position-history subquery unchanged for a separate history-specific scope review.

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
is a maintainability hardening slice that keeps snapshot-side mismatch evidence aligned with the
governed current-epoch snapshot scope.
