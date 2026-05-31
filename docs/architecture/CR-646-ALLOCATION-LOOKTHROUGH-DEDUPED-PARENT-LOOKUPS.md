# CR-646: Allocation Look-Through Deduped Parent Lookups

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Asset-allocation look-through builds one resolved allocation input per returned holding row. In
portfolio-list or business-unit scopes, the same fund/security parent can appear in more than one
portfolio, which meant the look-through repository could receive duplicate parent security IDs and
inflate the `IN` predicate without changing decomposition semantics.

## Change

Deduplicated normalized parent security IDs before the look-through component repository call and
added repository-level defensive deduplication for direct callers. Allocation assembly still
processes every returned holding row, so duplicated holdings across portfolios continue to
contribute independently to exposure totals.

## Impact

This reduces look-through component lookup parameter volume for multi-portfolio asset-allocation
reads while preserving direct and look-through allocation totals, decomposed position counts,
component weighting behavior, response shape, and source-data product semantics.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal read-scope hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
