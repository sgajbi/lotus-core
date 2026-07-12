# CR-563: Benchmark Composition Latest Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Benchmark composition source-data reads resolve effective benchmark constituents and then retain
the latest row for each benchmark/index pair. The query filters by benchmark identity and effective
window, orders by benchmark and index, and the repository deduplicates by `benchmark_id` plus
`index_id`.

The table only declared a broad `(benchmark_id, composition_effective_from,
composition_effective_to)` index. That helps window filtering but does not match the latest
effective row access path by benchmark/index.

## Change

Added `ix_bench_comp_benchmark_index_eff` on:

1. `benchmark_id`
2. `index_id`
3. `composition_effective_from DESC`
4. `composition_effective_to`

The index is declared in model metadata and created by Alembic revision `c0fcc3d4e5f6`. Repository
query-shape coverage now pins the benchmark, effective-window, and benchmark/index ordering used by
multi-benchmark composition reads.

## Impact

The change keeps benchmark composition source-data reads aligned to the deduplication key used by
the governed composition window contract. No API route shape or platform contract changed.
Repo-local wiki source changed, but wiki publication must wait until this branch is merged to
`main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q` - 17 passed
3. `python -m alembic heads` - `c0fcc3d4e5f6 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. `python scripts/test_manifest.py --suite unit-db --quiet` - 9 passed
6. touched-surface `ruff check` - passed
7. touched-surface `ruff format --check` - passed
8. `git diff --check` - passed
9. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected `Database-Migrations.md` publication drift on this unmerged branch
