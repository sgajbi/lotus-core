# CR-704: Portfolio Summary Cash Valuation Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`get_portfolio_summary(...)` read the latest snapshot rows, then built cash-account balance
records before starting portfolio-summary reporting-currency valuation across the same snapshot
rows. Those two evidence calculations are independent once the portfolio, resolved date, reporting
currency, and snapshot rows are known, so the portfolio-summary API paid avoidable sequential
latency across cash-account evidence reads and FX-backed valuation conversion.

## Change

Routed cash-account record construction and snapshot reporting-value conversion through a single
`asyncio.gather(...)` phase after snapshot rows are loaded. Existing cash-account master fallback,
FX conversion, valuation-status classification, and summary totals remain unchanged.

Added focused reporting-service coverage that proves cash-account balance construction and
snapshot reporting-value conversion start concurrently.

## Impact

This reduces `PortfolioSummary` latency for portfolios with cash-account evidence and reporting
currency conversion while preserving portfolio/date validation, no-business-date behavior, cash
account fallback behavior, valuation counts, totals, response contracts, database schema, wiki
source, and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service portfolio-summary proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
