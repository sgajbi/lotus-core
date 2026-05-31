# CR-566: DPM Mandate Binding SQL Ranking

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`list_dpm_portfolio_universe_candidates(...)` fetched all effective discretionary mandate binding
rows that matched the source-data filters, deduplicated the latest row per `(portfolio_id,
mandate_id)` in Python, then applied cursor pagination and limit in Python.

That shape made DPM universe candidate reads materialize superseded effective rows and rows before
the requested cursor even though only one latest row per mandate binding could be returned.

## Change

Added `_ranked_portfolio_mandate_binding_ids(...)` and routed these reads through it:

1. `list_model_portfolio_affected_mandates(...)`
2. `list_dpm_portfolio_universe_candidates(...)`

The helper ranks source rows with `row_number()` partitioned by portfolio and mandate, ordered by
effective date, observed timestamp, binding version, update/create timestamp, and durable row id.
Both reads now return only `rn = 1`. The DPM universe candidate read also pushes its cursor and
limit into SQL after latest-row selection.

## Impact

This reduces DPM source-data product read amplification without changing response shape, active
authority filtering, source predicates, final portfolio/mandate ordering, API route shape, database
schema, wiki source, or platform contracts.

No new index was added. The active DPM path already has the partial
`ix_mandate_binding_dpm_model_book_eff` index on model, booking center, effective window,
portfolio, and mandate for active discretionary authority rows.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fcc3d4e5f6 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
7. `git diff --check` - passed
8. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected `Database-Migrations.md` publication drift from earlier unmerged migration guidance
