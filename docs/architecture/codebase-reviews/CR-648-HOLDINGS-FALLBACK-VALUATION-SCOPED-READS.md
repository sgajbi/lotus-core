# CR-648: Holdings Fallback Valuation Scoped Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Holdings reads merge latest snapshot rows with position-history fallback rows when snapshot
materialization lags reprocessing. When only a small set of history-backed securities needed
valuation enrichment, the fallback repository query still ranked latest snapshot valuation rows for
the whole portfolio.

## Change

Added optional security-id scoping to latest snapshot valuation map repository helpers and routed
holdings fallback valuation reads with the exact normalized history-backed securities that need
enrichment. The helpers keep their unfiltered default for compatibility with direct callers.

## Impact

This reduces fallback snapshot ranking and row transfer for broad portfolios while preserving
holdings assembly, history-backed valuation continuity, reprocessing status, held-since handling,
market-price freshness checks, response shape, and source-data product metadata.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal read-scope hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_unit_query_position_repo.py tests/unit/services/query_service/services/test_position_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
