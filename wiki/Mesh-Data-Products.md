# Mesh Data Products

## Mesh role

`lotus-core` is a maturity-wave producer in the Lotus enterprise data mesh.

## Governed product

- Product ID: `lotus-core:PortfolioStateSnapshot:v1`
- Product role: authoritative portfolio state snapshot for downstream performance, risk, advisory, reporting, management, gateway, and Workbench discovery flows
- Source declaration: `contracts/domain-data-products/`
- Trust telemetry: `contracts/trust-telemetry/`

## Active DPM Source Products

RFC-087 Slices 4 through 8 promote the first DPM source products for `lotus-manage` discretionary
mandate portfolio management.

These products support discretionary mandate portfolio management rather than advisor proposal
generation. In business terms, `lotus-core` supplies the governed facts that a portfolio manager
needs before `lotus-manage` can calculate a rebalance: the approved model, the mandate authority,
the investable/restricted universe, tax lots, market prices, and FX coverage. `lotus-manage` remains
the execution and decisioning application; `lotus-core` remains the source-data authority.

| Product | Route | Purpose | Current proof |
| --- | --- | --- | --- |
| `DpmModelPortfolioTarget:v1` | `/integration/model-portfolios/{model_portfolio_id}/targets` | Approved effective-dated model portfolio target weights, min/max bands, lineage, and supportability for stateful DPM source assembly. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |
| `DiscretionaryMandateBinding:v1` | `/integration/portfolios/{portfolio_id}/mandate-binding` | Effective-dated portfolio mandate, model, policy, authority, jurisdiction, booking center, tax-awareness, settlement-awareness, and rebalance constraints. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |
| `InstrumentEligibilityProfile:v1` | `/integration/instruments/eligibility-bulk` | Bulk product-shelf, restriction, liquidity, issuer, and settlement eligibility for held and target instruments. | Implemented in core with ingestion, persistence, OpenAPI, source-product metadata, tests, and canonical seed data. Live canonical runtime proof is pending stack refresh. |
| `PortfolioTaxLotWindow:v1` | `/integration/portfolios/{portfolio_id}/tax-lots` | Portfolio-window tax lots and cost-basis state for tax-aware DPM sell decisions without production per-security fan-out. | Implemented in core using `position_lot_state`, deterministic cursor paging, OpenAPI, source-product metadata, supportability, and tests. Live canonical runtime proof is pending stack refresh. |
| `MarketDataCoverageWindow:v1` | `/integration/market-data/coverage` | Held and target universe price and FX coverage diagnostics for valuation, drift, cash conversion, and rebalance sizing. | Implemented in core using `market_prices` and `fx_rates`, stale/missing supportability, OpenAPI, source-product metadata, and tests. Live canonical runtime proof is pending stack refresh. |

```mermaid
flowchart LR
    Upstream[Investment office model system] --> Ingest[core ingest model-portfolios and targets]
    Mandate[Mandate administration and policy engine] --> BindIngest[core ingest mandate-bindings]
    Eligibility[Product shelf, restriction, issuer, liquidity, and settlement sources] --> EligibilityIngest[core ingest instrument-eligibility]
    Booking[Booking and transaction processing] --> LotState[(position_lot_state)]
    Market[Market price and FX sources] --> MarketStore[(market_prices and fx_rates)]
    Ingest --> Store[(model_portfolio_definitions and model_portfolio_targets)]
    BindIngest --> BindingStore[(portfolio_mandate_bindings)]
    EligibilityIngest --> EligibilityStore[(instrument_eligibility_profiles)]
    Store --> API[core-control DpmModelPortfolioTarget:v1]
    BindingStore --> BindingAPI[core-control DiscretionaryMandateBinding:v1]
    EligibilityStore --> EligibilityAPI[core-control InstrumentEligibilityProfile:v1]
    LotState --> TaxLotAPI[core-control PortfolioTaxLotWindow:v1]
    MarketStore --> MarketAPI[core-control MarketDataCoverageWindow:v1]
    API --> Manage[lotus-manage DPM source assembler]
    BindingAPI --> Manage
    EligibilityAPI --> Manage
    TaxLotAPI --> Manage
    MarketAPI --> Manage
```

## Audience Guide

| Audience | How to use this page |
| --- | --- |
| Business and product | Use the active product table to explain what governed data supports discretionary mandate portfolio management and why stateful execution is not promoted until every source family is ready. |
| Sales and client demos | Use the diagram to describe how the platform separates source-data authority from rebalance decisioning. Do not present stateful `lotus-manage` execution as live-certified until proof status changes from pending to passed. |
| Operations | Use the proof posture and operating rule sections to understand whether an incident is a source-data availability issue, a stale/missing-data issue, or a management execution issue. |
| Developers and architects | Use the route and product names as the integration contract. New DPM needs should extend the product-specific catalog rather than creating a monolithic execution-context endpoint. |

## Proof Posture

Current implementation proof is local and CI-backed, with live canonical proof pending.

| Proof area | Current state |
| --- | --- |
| Source-product implementation | Implemented for model targets, mandate binding, instrument eligibility, portfolio tax lots, and market-data/FX coverage. |
| Local validation | Source-data product guard, domain-product validation, focused validator tests, OpenAPI contract tests, and product-specific service/router tests exist. |
| Reusable live validation | `make live-dpm-source-validate` runs `scripts/validate_live_dpm_source_products.py` against `core-control.dev.lotus`. |
| Latest live attempt | Blocked: `core-control.dev.lotus` refused connections on 2026-05-02, so no endpoint-level live proof was accepted. |
| Stateful `lotus-manage` promotion | Blocked until all five products pass live validation, a source-family readiness/supportability product is available, and `lotus-manage` proves stateful source assembly end to end. |

```mermaid
flowchart TD
    Seed[Canonical front-office seed PB_SG_GLOBAL_BAL_001] --> CoreProducts[Five DPM source products]
    CoreProducts --> LiveValidator[make live-dpm-source-validate]
    LiveValidator --> Evidence{Live evidence accepted?}
    Evidence -->|No, runtime unavailable or data incomplete| Blocked[Keep stateful manage promotion blocked]
    Evidence -->|Yes| Readiness[DPM source-family readiness/supportability]
    Readiness --> ManageProof[lotus-manage stateful source assembly proof]
    ManageProof --> Promote[Capability truth may advertise stateful portfolio_id execution]
```

## Future DPM Source Products

All first-wave RFC-087 DPM source-product declarations are now active. New proposed products should
be added only through a follow-up RFC or explicit RFC-087 extension with implementation evidence.

There are currently no remaining planned DPM source products in the in-code planned catalog.

## Platform relationship

`lotus-platform` aggregates the repo-native declaration, validates trust telemetry, applies mesh SLO/access/evidence policies, and includes this product in generated catalog, dependency graph, live certification, maturity matrix, evidence packs, and RFC-0092 operating reports.

## Operating rule

Do not duplicate product authority in gateway, Workbench, or platform. Changes to portfolio-state product identity, lifecycle, telemetry, or evidence must start in `lotus-core` and then pass platform mesh certification.

For RFC-087 specifically, do not add a single "DPM execution context" endpoint to core. Core should
continue to expose governed source products with clear ownership and supportability. Composition
belongs in `lotus-manage`, and downstream routing belongs in Gateway after the manage contract is
certified.
