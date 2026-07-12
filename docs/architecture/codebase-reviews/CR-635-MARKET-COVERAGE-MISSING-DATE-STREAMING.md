# CR-635: Market Coverage Missing-Date Streaming

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Market/reference coverage response assembly materialized the full expected date set for every
requested window before computing the missing-date count and first ten missing dates. Broad coverage
windows therefore allocated memory proportional to the full date range even though the response only
needs a count and a small diagnostic sample.

## Change

Added a streaming expected-date iterator, direct expected-date count calculation, and a bounded
missing-date summary helper. The response builder now walks the expected window once and retains
only the first ten missing dates.

## Impact

This reduces memory pressure for broad source-data coverage reports while preserving observed-date
fallback behavior, data-quality classification, missing-date count, missing-date sample ordering,
runtime metadata, and response shape.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal response-assembly performance hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
