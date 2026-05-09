# lotus-core Methodology Index

This index collects implementation-backed methodology notes for source-data products where
downstream applications need auditable formulas, boundaries, and non-claims.

## Source-Data Products

| Product | Methodology | Scope |
| --- | --- | --- |
| `PortfolioCashflowProjection:v1` | [Portfolio Cashflow Projection](./source-data-products/portfolio-cashflow-projection.md) | Operational daily and total cashflow projection, booked-only/projected modes, and non-claims for liquidity ladders, tax, performance, market impact, and OMS execution. |
| `PortfolioTaxLotWindow:v1` | [Portfolio Tax Lot Window](./source-data-products/portfolio-tax-lot-window.md) | Effective-dated open and closed tax-lot state, cost-basis evidence, deterministic paging, and non-claims for jurisdiction-specific tax advice, realized-tax optimization, and client-tax approval. |
| `TransactionCostCurve:v1` | [Transaction Cost Curve](./source-data-products/transaction-cost-curve.md) | Observed booked-fee aggregation by security, transaction type, and currency, with non-claims for market impact, venue routing, best execution, OMS acknowledgement, and minimum-cost execution methodology. |
