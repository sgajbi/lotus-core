# CR-631: Portfolio Analytics Paged Position Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Portfolio analytics-timeseries input generation resolved observation dates by loading all
position-timeseries rows across the requested window before applying date pagination. Large
portfolio windows could therefore materialize many more position rows than the page being returned,
even though downstream cashflow, FX, and response assembly work only needs the current page dates
plus latest prior EOD values for continuity.

## Change

Added a repository helper to list position observation dates using the same portfolio, date,
snapshot-epoch, position-state, and current-history quantity scope as the row read. The portfolio
analytics service now uses observation dates to select the page first, then reads position rows only
for that page window and resolves latest prior EOD rows through the existing latest-before helper.

Fallback behavior remains for test doubles or alternate repositories without the new helper.

## Impact

This reduces API read amplification for portfolio analytics input generation while preserving
pagination semantics, snapshot epoch behavior, day-boundary continuity, cashflow handling, FX
conversion, response shape, and quality diagnostics.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal read-path performance hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
