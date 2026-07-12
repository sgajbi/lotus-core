# CR-594: Liquidity Ladder Snapshot Partition

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The liquidity ladder response path split snapshot rows with two list comprehensions: one for cash
rows and one for non-cash rows. That called cash classification twice for non-cash positions,
repeating asset-class normalization across the same high-use portfolio liquidity support query.

## Change

Added a single-pass `_partition_cash_rows(...)` helper and routed liquidity ladder response assembly
through it. Focused coverage proves each source row is classified exactly once while preserving the
cash/non-cash split.

## Impact

This removes repeated per-row classification work from liquidity ladder calculation support without
changing API route shape, response fields, OpenAPI contracts, database schema, wiki source, or
platform contracts.

No wiki update was needed because this is internal calculation-path optimization with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_liquidity_ladder_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
