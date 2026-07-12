# CR-552: Current Epoch Snapshot Date Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository latest current-epoch snapshot date reads.

## Finding

`OperationsRepository.get_latest_snapshot_date_for_current_epoch(...)` and
`get_latest_snapshot_date_for_current_epoch_as_of(...)` repeated the same high-volume
daily-position-snapshot to position-state join, portfolio scope, and dual snapshot/state timestamp
fence. Only the optional business-date upper bound differed.

These helpers support timestamped operations overview evidence, so keeping the current-epoch join
and observation-time fence in two places increases the risk of drift between latest snapshot and
booked-date snapshot evidence.

## Change

1. Added `_current_epoch_snapshot_date_stmt(...)` to build the shared current-epoch snapshot-date
   query.
2. Reused it from both latest current-epoch snapshot date helpers.
3. Preserved the snapshot-to-position-state join, normalized security match, epoch match, portfolio
   predicate, optional business-date bound, dual `created_at`/`updated_at` timestamp fence, scalar
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
is a maintainability hardening slice that keeps latest and booked current-epoch snapshot evidence
aligned to one governed query scope.
