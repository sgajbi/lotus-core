# CR-569: Client Governance Profile SQL Ranking

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Client restriction and sustainability preference source-data reads filtered by portfolio, client,
effective window, optional mandate, and active status, but then materialized superseded effective
rows and selected the latest row per business key in Python.

Both tables already have active-status partial indexes aligned to the source-data predicates and
latest-effective ordering, so keeping deduplication outside SQL created avoidable read
amplification.

## Change

Added `_ranked_latest_effective_ids(...)` as a reusable repository helper for effective-dated
source tables, then routed these reads through SQL `row_number()` latest-row selection:

1. `list_client_restriction_profiles(...)`
2. `list_sustainability_preference_profiles(...)`

The ranking partitions by the product business key and orders by effective date, observed
timestamp, source version, update timestamp, create timestamp, and durable row id. Final response
ordering by restriction scope/code or preference framework/code is preserved.

## Impact

This reduces client governance source-data read amplification and removes duplicated Python
latest-row selection for these two evidence classes without changing response shape, active-status
defaults, source predicates, API route shape, database schema, wiki source, or platform contracts.

No new index was added. Existing active-status partial indexes already match the source-data query
shape.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
