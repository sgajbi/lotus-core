# CR-559: Lineage History Snapshot Latest Indexes

Date: 2026-05-31

## Scope

Position-history and daily-position-snapshot indexing for query-service lineage key support reads.

## Finding

`OperationsRepository.get_lineage_keys(...)` resolves latest position-history and latest
daily-snapshot evidence for each `PositionState` row. Both correlated subqueries use the same
lineage access pattern:

1. equality on portfolio,
2. equality on normalized security,
3. equality on epoch,
4. latest business-date lookup.

Existing raw-portfolio API indexes support portfolio plus normalized security with descending date
ordering, but place `epoch` after the date/id ordering. Existing normalized calculation indexes
place `epoch` before the date but use `trim(portfolio_id)` rather than the raw portfolio predicate
used by the lineage query. That left the lineage support listing without exact indexes for its
per-row latest history and snapshot evidence lookups.

## Change

1. Added model metadata index `ix_pos_hist_lineage_latest` on `position_history(portfolio_id,
   trim(security_id), epoch, position_date DESC)`.
2. Added model metadata index `ix_daily_snap_lineage_latest` on
   `daily_position_snapshots(portfolio_id, trim(security_id), epoch, date DESC)`.
3. Added Alembic revision `c0f9a0b1c2d3` to create and drop both indexes.
4. Strengthened database model tests to pin both index expression orders.
5. Updated repo-local migration guidance to cover lineage latest evidence indexes across history,
   snapshot, and valuation-job evidence.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python scripts/test_manifest.py --suite unit-db --quiet`
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
8. `git diff --check`

Results:

1. Focused model/index metadata proof passed.
2. Focused operations repository query-shape proof passed.
3. Alembic reported a single current head.
4. Migration SQL contract smoke passed.
5. Unit-DB manifest passed.
6. Touched-surface ruff passed.
7. Touched-surface format check passed.
8. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape or platform contract change was required. The repo-local wiki source changed
because database migration guidance now covers lineage latest evidence indexes. Do not publish the
wiki from this unmerged feature branch.
