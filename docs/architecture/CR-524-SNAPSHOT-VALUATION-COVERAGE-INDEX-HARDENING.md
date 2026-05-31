# CR-524: Snapshot Valuation Coverage Index Hardening

Date: 2026-05-31

## Scope

Query-service operations support reads for snapshot valuation coverage.

## Finding

`get_snapshot_valuation_coverage_summary(...)` filters daily position snapshots by portfolio and
snapshot date, joins position state by normalized security and epoch, and counts valued positions
with a non-`UNVALUED` valuation status. The table had generic portfolio/date and normalized-security
indexes, but no index aligned to the coverage-summary filter and join shape. The valued-position
predicate also wrapped `daily_position_snapshots.valuation_status` in `upper(trim(...))`, despite
the table carrying a raw status index and a governed uppercase default.

## Change

1. Added Alembic migration `c0f7a8b9c0d1_perf_add_snapshot_valuation_coverage_index.py` to
   normalize historical snapshot valuation statuses and add
   `ix_daily_snap_port_date_status_norm_sec_epoch`.
2. Declared the same index in SQLAlchemy model metadata.
3. Changed snapshot valuation coverage summary predicates to compare directly against stored
   governed valuation statuses.
4. Updated model and operations repository query-shape proof.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/c0f7a8b9c0d1_perf_add_snapshot_valuation_coverage_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/c0f7a8b9c0d1_perf_add_snapshot_valuation_coverage_index.py`
7. `git diff --check`

Results:

1. Focused operations/model proof passed.
2. Alembic head proof passed.
3. Migration SQL smoke passed.
4. Unit-db migration apply suite passed.
5. Touched-surface ruff passed.
6. Touched-surface format check passed.
7. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is support-query
predicate and index hardening for existing snapshot valuation coverage APIs.
