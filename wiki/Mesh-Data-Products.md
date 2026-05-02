# Mesh Data Products

## Mesh role

`lotus-core` is a maturity-wave producer in the Lotus enterprise data mesh.

## Governed product

- Product ID: `lotus-core:PortfolioStateSnapshot:v1`
- Product role: authoritative portfolio state snapshot for downstream performance, risk, advisory, reporting, management, gateway, and Workbench discovery flows
- Source declaration: `contracts/domain-data-products/`
- Trust telemetry: `contracts/trust-telemetry/`

## Active DPM Source Products

RFC-087 Slice 4 promotes the first DPM source product for `lotus-manage` discretionary mandate
portfolio management.

| Product | Route | Purpose | Current proof |
| --- | --- | --- | --- |
| `DpmModelPortfolioTarget:v1` | `/integration/model-portfolios/{model_portfolio_id}/targets` | Approved effective-dated model portfolio target weights, min/max bands, lineage, and supportability for stateful DPM source assembly. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |

```mermaid
flowchart LR
    Upstream[Investment office model system] --> Ingest[core ingest model-portfolios and targets]
    Ingest --> Store[(model_portfolio_definitions and model_portfolio_targets)]
    Store --> API[core-control DpmModelPortfolioTarget:v1]
    API --> Manage[lotus-manage DPM source assembler]
```

## Proposed DPM Source Products

RFC-087 adds proposed source-product declarations for `lotus-manage` discretionary mandate
portfolio management. These products are not runtime APIs until their endpoint slices are
implemented and promoted to active status.

| Product | Planned route | Purpose |
| --- | --- | --- |
| `DiscretionaryMandateBinding:v1` | `/integration/portfolios/{portfolio_id}/mandate-binding` | Effective-dated portfolio mandate, model, policy, jurisdiction, and rebalance authority binding. |
| `InstrumentEligibilityProfile:v1` | `/integration/instruments/eligibility-bulk` | Bulk product-shelf, restriction, liquidity, and settlement eligibility for held and target instruments. |
| `PortfolioTaxLotWindow:v1` | `/integration/portfolios/{portfolio_id}/tax-lots` | Portfolio-window tax lots and cost-basis state for tax-aware DPM sell decisions. |
| `MarketDataCoverageWindow:v1` | `/integration/market-data/coverage` | Price and FX coverage diagnostics for the held and target mandate universe. |

These proposed products are declared in
`contracts/domain-data-products/lotus-core-products.v1.json` with lifecycle status `proposed`.
Their planned in-code product catalog and source-security posture live in
`portfolio_common.source_data_products` and `portfolio_common.source_data_security`.

## Platform relationship

`lotus-platform` aggregates the repo-native declaration, validates trust telemetry, applies mesh SLO/access/evidence policies, and includes this product in generated catalog, dependency graph, live certification, maturity matrix, evidence packs, and RFC-0092 operating reports.

## Operating rule

Do not duplicate product authority in gateway, Workbench, or platform. Changes to portfolio-state product identity, lifecycle, telemetry, or evidence must start in `lotus-core` and then pass platform mesh certification.
