# lotus-core Methodology Index

This index collects implementation-backed methodology notes for source-data products where
downstream applications need auditable formulas, boundaries, and non-claims.

## Source-Data Products

| Product | Methodology | Scope |
| --- | --- | --- |
| `HoldingsAsOf:v1` | [Holdings As Of](./source-data-products/holdings-as-of.md) | Governed position and cash-balance state, current-epoch snapshot reconciliation, history-backed supplement rows, valuation continuity, cash reporting-currency restatement, freshness posture, and non-claims for liquidity, performance, risk, tax, and execution methodology. |
| `MarketDataCoverageWindow:v1` | [Market Data Coverage Window](./source-data-products/market-data-coverage-window.md) | Held and target universe price and FX coverage diagnostics, freshness supportability, missing/stale evidence posture, and non-claims for valuation, FX attribution, liquidity, execution quality, and OMS acknowledgement. |
| `DpmSourceReadiness:v1` | [DPM Source Readiness](./source-data-products/dpm-source-readiness.md) | Fail-closed DPM source-family readiness over mandate binding, model targets, eligibility, tax lots, and market-data coverage, with non-claims for mandate approval, valuation, suitability, liquidity, execution, and OMS acknowledgement. |
| `TransactionLedgerWindow:v1` | [Transaction Ledger Window](./source-data-products/transaction-ledger-window.md) | Governed booked transaction-row windowing, filters, linked row evidence, reporting-currency restatement, data-quality posture, and non-claims for tax, FX attribution, cash aggregation, transaction-cost methodology, and execution quality. |
| `PortfolioCashflowProjection:v1` | [Portfolio Cashflow Projection](./source-data-products/portfolio-cashflow-projection.md) | Operational daily and total cashflow projection, booked-only/projected modes, and non-claims for liquidity ladders, tax, performance, market impact, and OMS execution. |
| `PortfolioLiquidityLadder:v1` | [Portfolio Liquidity Ladder](./source-data-products/portfolio-liquidity-ladder.md) | Source-owned cash-availability buckets and non-cash asset liquidity-tier exposure, with non-claims for advice, funding recommendation, OMS execution, tax, best execution, and market-impact forecasting. |
| `PortfolioTaxLotWindow:v1` | [Portfolio Tax Lot Window](./source-data-products/portfolio-tax-lot-window.md) | Effective-dated open and closed tax-lot state, cost-basis evidence, deterministic paging, and non-claims for jurisdiction-specific tax advice, realized-tax optimization, and client-tax approval. |
| `TransactionCostCurve:v1` | [Transaction Cost Curve](./source-data-products/transaction-cost-curve.md) | Observed booked-fee aggregation by security, transaction type, and currency, with non-claims for market impact, venue routing, best execution, OMS acknowledgement, and minimum-cost execution methodology. |
