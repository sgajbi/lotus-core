# CR-688: Realized Tax Summary Parallel Currency Conversions

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService.get_realized_tax_summary(...)` already reads the source transaction count and
realized-tax evidence concurrently, but then converted each currency bucket into the requested
reporting currency sequentially. Multi-currency tax evidence therefore serialized independent FX
conversion work after the database reads completed.

## Change

Resolved realized-tax currency-bucket reporting conversions with `asyncio.gather(...)` and summed
the converted values from the gathered result. Empty-evidence behavior remains unchanged: a
requested reporting currency still produces a zero total after summing an empty conversion set.

Added focused coverage that proves two currency-bucket conversions must start concurrently.

## Impact

This reduces `PortfolioRealizedTaxSummary` latency for multi-currency tax evidence while
preserving portfolio validation, default as-of-date resolution, currency normalization,
same-currency identity conversion, response shape, source-data runtime metadata, database schema,
wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused realized-tax summary proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
