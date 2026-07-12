# CR-640: Position Timeseries Page-Scoped FX

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Position analytics-timeseries assembly fetched portfolio-to-reporting and position-to-portfolio FX
maps for the full requested analytics window before applying row pagination. Large windows could
therefore read FX evidence for dates and lookahead rows outside the returned page, and missing FX on
non-returned dates could fail an otherwise valid page.

## Change

Moved position-timeseries FX reads after page slicing and scoped both conversion maps to the
returned page dates and returned page currencies. The existing `page_size + 1` lookahead still
drives pagination, but no longer expands FX evidence reads.

## Impact

This reduces FX read amplification for broad position analytics windows while preserving
snapshot-epoch handling, cursor semantics, cashflow lookups, continuity repair, missing-FX behavior
for returned rows, response shape, and source-data metadata.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal analytics input response-assembly performance
hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
