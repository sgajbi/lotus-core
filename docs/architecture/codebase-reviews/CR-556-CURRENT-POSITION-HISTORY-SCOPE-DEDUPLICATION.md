# CR-556: Current Position History Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository current-position-history evidence reads.

## Finding

Two support-plane reads still hand-built the same current-position-history to position-state scope:

1. `OperationsRepository.get_position_snapshot_history_mismatch_count(...)` for the latest-history
   side of snapshot/history mismatch evidence.
2. Reset-watermark reprocessing job eligibility, where the repository verifies that a pending reset
   job still maps to an open current position-history slice before exposing it to operators.

Both paths joined `PositionHistory` to `PositionState` by portfolio, normalized security, and epoch.
The mismatch path also carried a dual response-snapshot timestamp fence, while the reset-watermark
path added payload-security and impacted-date predicates. Keeping the common join and portfolio
scope local in both places left support evidence exposed to future predicate drift.

## Change

1. Added `_apply_current_position_history_scope(...)` to centralize the current-position-history to
   position-state join, portfolio predicate, optional normalized-security predicate, optional
   position-date upper bound, and optional history/state timestamp fence.
2. Reused the helper from the mismatch-count latest-history subquery.
3. Reused the helper from reset-watermark reprocessing job portfolio-scope eligibility while
   preserving the payload security correlation, impacted-date bound, row-number ordering, and
   positive-quantity eligibility check.
4. Strengthened query-shape tests to pin the current-position-history portfolio predicate on both
   affected support reads.

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
keeps current-position-history support evidence aligned across mismatch diagnostics and
reset-watermark reprocessing job eligibility.
