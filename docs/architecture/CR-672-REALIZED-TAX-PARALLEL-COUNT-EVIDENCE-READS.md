# CR-672: Realized Tax Parallel Count Evidence Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionService.get_realized_tax_summary(...)` read the full source-window transaction count and
the explicit realized-tax evidence rows sequentially after portfolio currency and effective-date
resolution. The count query and sparse tax-evidence row query are independent; the service only
combines them later for metadata and aggregation.

## Change

The service now reads the source-window count and explicit tax-evidence transactions with
`asyncio.gather(...)`. Realized-tax aggregation, FX restatement, data-quality status,
latest-evidence timestamp derivation, source-data product identity, and response shape are
unchanged.

Added service coverage that would deadlock under sequential execution, proving the two repository
reads are started concurrently.

## Impact

This reduces `PortfolioRealizedTaxSummary:v1` latency on tax evidence windows without changing
route shape, response contracts, database schema, source-data product metadata, wiki source, or
platform contracts.

## Validation

Local validation passed:

1. focused transaction service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
