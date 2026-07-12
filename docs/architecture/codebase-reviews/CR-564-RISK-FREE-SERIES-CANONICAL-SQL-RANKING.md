# CR-564: Risk-Free Series Canonical SQL Ranking

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`RiskFreeSeriesWindow` reads fetched every risk-free curve/source row for a currency/date window
and then selected the canonical row per date in Python. The canonical precedence is meaningful:
accepted quality wins, then freshest source timestamp, then stable source identifiers. Keeping that
selection in Python forced large market/reference windows to transfer and materialize superseded
provider rows that the source-data product never returned.

## Change

Moved canonical risk-free row selection into SQL using `row_number()` partitioned by `series_date`.
The ranking preserves the existing repository precedence:

1. accepted `quality_status`
2. latest `source_timestamp`
3. descending `series_id`
4. descending `source_vendor`
5. descending `source_record_id`
6. descending durable row `id`

The final result remains ordered by ascending `series_date`.

## Impact

This reduces risk-free source-data product read amplification without changing response shape,
quality precedence, date ordering, API route shape, database schema, wiki source, or platform
contract. No wiki update was needed because no migration or operator schema guidance changed.

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
