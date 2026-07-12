# CR-636: Portfolio Timeseries Missing-Date Count

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Portfolio analytics-timeseries diagnostics built a sorted list of every missing expected business
date even though the response only exposes `missing_dates_count`. Broad windows therefore paid
unnecessary allocation and sorting cost during API response assembly.

## Change

Changed diagnostics assembly to build one observed-date set and stream expected business dates into
a count, avoiding the unused missing-date list.

## Impact

This reduces response-assembly memory and sort work for broad portfolio analytics input requests
while preserving diagnostics, data-quality classification, pagination, response shape, and source
data product metadata.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal response-assembly performance hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
