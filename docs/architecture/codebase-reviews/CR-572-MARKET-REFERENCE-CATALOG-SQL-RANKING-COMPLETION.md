# CR-572: Market Reference Catalog SQL Ranking Completion

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After the source-data ranking hardening for DPM and client products, the reference-data repository
still used Python latest-row selection for market/reference catalog reads:

1. benchmark definitions,
2. index definitions,
3. benchmark composition rows for one benchmark,
4. benchmark composition rows for a benchmark set.

These reads serve API and source-data consumers that need the current effective benchmark and index
catalog. Fetching superseded effective rows and discarding them after materialization is avoidable
read amplification.

## Change

Routed these market/reference catalog reads through `_ranked_latest_effective_ids(...)` with SQL
`row_number()` latest-row ranking.

The ranking partitions by the relevant catalog business key:

1. `benchmark_id`,
2. `index_id`,
3. `benchmark_id` and `index_id` for benchmark composition.

The query predicates, currency/status normalization, date-window filters, and final ordering are
preserved. The now-unused Python `_latest_effective_rows(...)` helper was removed so future hot
paths do not drift back to materializing superseded rows.

## Impact

Benchmark/index catalog and composition reads now return only latest effective business rows from
SQL. This aligns the repository with existing active definition and benchmark-composition latest
indexes, reduces read amplification, and removes the last generic Python latest-effective
deduplication path from the reference-data repository.

No API route shape, response DTO, database schema, or platform contract changed.

Repo-local supported-features wiki source was updated to keep the product-facing performance
posture current. Wiki publication must wait until after this branch is merged to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
7. `git diff --check` - passed
8. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected unmerged-branch published wiki drift for `_Sidebar.md`, `Database-Migrations.md`, `Home.md`, and `Supported-Features.md`
