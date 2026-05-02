# Mesh Data Products

## Mesh role

`lotus-core` is a maturity-wave producer in the Lotus enterprise data mesh.

## Governed product

- Product ID: `lotus-core:PortfolioStateSnapshot:v1`
- Product role: authoritative portfolio state snapshot for downstream performance, risk, advisory, reporting, management, gateway, and Workbench discovery flows
- Source declaration: `contracts/domain-data-products/`
- Trust telemetry: `contracts/trust-telemetry/`

## Active DPM Source Products

RFC-087 Slices 4 through 7 promote the first DPM source products for `lotus-manage` discretionary
mandate portfolio management.

| Product | Route | Purpose | Current proof |
| --- | --- | --- | --- |
| `DpmModelPortfolioTarget:v1` | `/integration/model-portfolios/{model_portfolio_id}/targets` | Approved effective-dated model portfolio target weights, min/max bands, lineage, and supportability for stateful DPM source assembly. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |
| `DiscretionaryMandateBinding:v1` | `/integration/portfolios/{portfolio_id}/mandate-binding` | Effective-dated portfolio mandate, model, policy, authority, jurisdiction, booking center, tax-awareness, settlement-awareness, and rebalance constraints. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |
| `InstrumentEligibilityProfile:v1` | `/integration/instruments/eligibility-bulk` | Bulk product-shelf, restriction, liquidity, issuer, and settlement eligibility for held and target instruments. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |
| `PortfolioTaxLotWindow:v1` | `/integration/portfolios/{portfolio_id}/tax-lots` | Portfolio-window tax lots and cost-basis state for tax-aware DPM sell decisions without production per-security fan-out. | Implemented in core using `position_lot_state`, deterministic cursor paging, OpenAPI, source-product metadata, supportability, and tests. Live canonical runtime proof is pending stack refresh. |

```mermaid
flowchart LR
    Upstream[Investment office model system] --> Ingest[core ingest model-portfolios and targets]
    Mandate[Mandate administration and policy engine] --> BindIngest[core ingest mandate-bindings]
    Eligibility[Product shelf, restriction, issuer, liquidity, and settlement sources] --> EligibilityIngest[core ingest instrument-eligibility]
    Booking[Booking and transaction processing] --> LotState[(position_lot_state)]
    Ingest --> Store[(model_portfolio_definitions and model_portfolio_targets)]
    BindIngest --> BindingStore[(portfolio_mandate_bindings)]
    EligibilityIngest --> EligibilityStore[(instrument_eligibility_profiles)]
    Store --> API[core-control DpmModelPortfolioTarget:v1]
    BindingStore --> BindingAPI[core-control DiscretionaryMandateBinding:v1]
    EligibilityStore --> EligibilityAPI[core-control InstrumentEligibilityProfile:v1]
    LotState --> TaxLotAPI[core-control PortfolioTaxLotWindow:v1]
    API --> Manage[lotus-manage DPM source assembler]
    BindingAPI --> Manage
    EligibilityAPI --> Manage
    TaxLotAPI --> Manage
```

## Proposed DPM Source Products

RFC-087 adds proposed source-product declarations for `lotus-manage` discretionary mandate
portfolio management. These products are not runtime APIs until their endpoint slices are
implemented and promoted to active status.

| Product | Planned route | Purpose |
| --- | --- | --- |
| `MarketDataCoverageWindow:v1` | `/integration/market-data/coverage` | Price and FX coverage diagnostics for the held and target mandate universe. |

This proposed product is declared in
`contracts/domain-data-products/lotus-core-products.v1.json` with lifecycle status `proposed`.
Its planned in-code product catalog and source-security posture live in
`portfolio_common.source_data_products` and `portfolio_common.source_data_security`.

## Platform relationship

`lotus-platform` aggregates the repo-native declaration, validates trust telemetry, applies mesh SLO/access/evidence policies, and includes this product in generated catalog, dependency graph, live certification, maturity matrix, evidence packs, and RFC-0092 operating reports.

## Operating rule

Do not duplicate product authority in gateway, Workbench, or platform. Changes to portfolio-state product identity, lifecycle, telemetry, or evidence must start in `lotus-core` and then pass platform mesh certification.
