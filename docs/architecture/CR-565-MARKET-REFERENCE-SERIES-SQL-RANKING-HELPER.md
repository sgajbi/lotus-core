# CR-565: Market Reference Series SQL Ranking Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Index price, index return, benchmark return, and risk-free series reads all used the same canonical
source-row precedence for duplicate business dates: accepted quality first, then freshest source
timestamp, stable source identifiers, and durable row id. Before this slice, most of those reads
fetched duplicate provider rows and canonicalized them in Python, while risk-free had a local SQL
ranking copy after CR-564.

That left repeated query policy in one repository and forced large market/reference source-data
windows to materialize superseded provider rows.

## Change

Added a shared `_canonical_series_ranked_subquery(...)` helper and routed these reads through it:

1. `list_index_price_points(...)`
2. `list_index_return_points(...)`
3. `list_benchmark_return_points(...)`
4. `list_index_price_series(...)`
5. `list_index_return_series(...)`
6. `list_risk_free_series(...)`

Each query now ranks rows with `row_number()` over the product-specific canonical key and returns
only `rn = 1`, while preserving existing final ordering by index/date, benchmark/date, or date.

## Impact

The change reduces market/reference source-data product read amplification and centralizes canonical
series-row precedence in one repository helper. Response shape, quality precedence, date ordering,
API route shape, database schema, wiki source, and platform contracts are unchanged.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fcc3d4e5f6 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `ruff check` - passed
6. touched-surface `ruff format --check` - passed
7. `git diff --check` - passed
8. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected `Database-Migrations.md` publication drift from earlier unmerged migration guidance
