# CR-561: Position Timeseries Latest-Before Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Analytics-input position time-series reads call
`list_latest_position_timeseries_before(...)` to fetch the latest row before a period start for
each requested security. The query filters by raw `portfolio_id`, normalized `security_id`, a
strict prior-date bound, and optional snapshot epoch, then ranks each security by `date DESC,
epoch DESC`.

Existing `position_timeseries` indexes either led with normalized portfolio expressions or placed
date ahead of normalized security. That left this prior-row support query without a composite index
matching its actual portfolio/security/date latest-row access pattern.

## Change

Added `ix_pos_ts_port_norm_sec_date_epoch` on:

1. `portfolio_id`
2. `trim(security_id)`
3. `date DESC`
4. `epoch DESC`

The index is declared in model metadata and created by Alembic revision `c0fbb2c3d4e5`. Repository
query-shape coverage now pins the raw portfolio predicate alongside the existing normalized
security, prior-date, snapshot-epoch, and latest-row ordering assertions.

## Impact

The change keeps prior-row analytics-input reads bounded to the requested portfolio and security
set while preserving response shape and snapshot semantics. No API route shape or platform
contract changed. Repo-local wiki source changed, but wiki publication must wait until this branch
is merged to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py -q` - 6 passed
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q` - 16 passed
3. `python -m alembic heads` - `c0fbb2c3d4e5 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. `python scripts/test_manifest.py --suite unit-db --quiet` - 9 passed
6. touched-surface `ruff check` - passed
7. touched-surface `ruff format --check` - passed
8. `git diff --check` - passed
9. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected `Database-Migrations.md` publication drift on this unmerged branch
