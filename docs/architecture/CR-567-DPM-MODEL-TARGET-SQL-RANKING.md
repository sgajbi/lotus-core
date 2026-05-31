# CR-567: DPM Model Target SQL Ranking

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`list_model_portfolio_targets(...)` fetched all effective target rows for a model portfolio version
and selected the latest row per instrument in Python.

That shape made DPM model-target source-data reads materialize superseded target rows that could
not be returned.

## Change

Added `_ranked_model_portfolio_target_ids(...)` and routed model-target reads through SQL
`row_number()` partitioned by `(model_portfolio_id, model_portfolio_version, instrument_id)`.

The query now returns only `rn = 1` rows and preserves final ordering by instrument id. Active target
filtering remains literal so the existing active-target partial index stays usable.

## Impact

This reduces DPM model target read amplification without changing response shape, active-target
default behavior, source predicates, API route shape, database schema, wiki source, or platform
contracts.

No new index was added. The active DPM target path already has
`ix_model_port_tgt_active_eff_order` on model, version, instrument, descending effective date, and
effective-to for active rows.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fcc3d4e5f6 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
7. `git diff --check` - passed
