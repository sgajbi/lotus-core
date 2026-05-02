# RFC 087 - DPM Source Data Products for lotus-manage Stateful Execution

| Field | Value |
| --- | --- |
| Status | Draft |
| Created | 2026-05-02 |
| Last Updated | 2026-05-02 |
| Owners | lotus-core engineering; lotus-manage engineering |
| Depends On | RFC 035; RFC 036; RFC 058; RFC 067; RFC 082; RFC 083; RFC 085; RFC 086; platform RFC-0082; platform RFC-0083; platform RFC-0084; platform RFC-0087; platform RFC-0091 |
| Related Standards | `docs/architecture/RFC-0082-contract-family-inventory.md`; `docs/architecture/RFC-0083-source-data-product-catalog.md`; `docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md`; `docs/architecture/RFC-0083-market-reference-data-target-model.md`; `docs/standards/route-contract-family-registry.json` |
| Scope | Cross-repo architecture and lotus-core implementation program |

## Executive Summary

`lotus-manage` RFC-0036 needs governed `lotus-core` source data for stateful discretionary
portfolio-management execution. The correct target architecture is not a single
`/dpm-execution-context` endpoint in `lotus-core`.

`lotus-core` must expose smaller, governed source-data products that `lotus-manage` can compose in
the same style used by `lotus-advise`: query-plane operational reads for canonical portfolio state,
control-plane integration products for governed source products, and explicit supportability
evidence for completeness and degraded posture.

This RFC defines the core enhancements required to unblock gold-standard `lotus-manage` stateful
execution without creating a monolithic context endpoint or moving DPM execution ownership into
`lotus-core`.

## Decision

`lotus-core` will not provide a single all-in-one DPM context endpoint.

Instead, `lotus-core` will:

1. certify the existing source-data products that already support stateful DPM input assembly,
2. add focused source-data products for DPM-specific gaps,
3. enhance ingestion so those products can be loaded, replayed, reconciled, and evidenced,
4. expose downstream APIs with source-data product metadata, OpenAPI quality, capability rules,
   access policy, observability, and trust telemetry aligned to Lotus mesh standards,
5. leave `lotus-manage` as the DPM execution and workflow owner.

`lotus-manage` will compose these products into its own `DpmCoreSourceContext` and execute simulate,
analyze, and async analyze locally.

## Non-Goals

This RFC does not:

1. add `POST /integration/portfolios/{portfolio_id}/dpm-execution-context`,
2. move DPM optimization, workflow gates, action-register logic, or run supportability into
   `lotus-core`,
3. make `lotus-core` responsible for discretionary rebalance recommendations,
4. introduce Gateway or Workbench integration work,
5. widen advisory proposal scope inside `lotus-manage`,
6. weaken the RFC-0082 query-service versus query-control-plane boundary.

## Current Evidence

### Existing deployed core routes

`core-control.dev.lotus` currently exposes these relevant control-plane routes:

1. `POST /integration/portfolios/{portfolio_id}/core-snapshot`,
2. `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`,
3. `POST /integration/portfolios/{portfolio_id}/analytics/reference`,
4. `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`,
5. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`,
6. `POST /integration/instruments/enrichment-bulk`,
7. `POST /integration/reference/classification-taxonomy`,
8. `POST /integration/benchmarks/{benchmark_id}/coverage`,
9. `POST /integration/reference/risk-free-series/coverage`,
10. `GET /support/portfolios/{portfolio_id}/readiness`,
11. `GET /lineage/portfolios/{portfolio_id}/keys`.

`core-query.dev.lotus` currently exposes these relevant query-plane routes:

1. `GET /portfolios/{portfolio_id}`,
2. `GET /portfolios/{portfolio_id}/positions`,
3. `GET /portfolios/{portfolio_id}/cash-balances`,
4. `GET /portfolios/{portfolio_id}/cash-accounts`,
5. `GET /portfolios/{portfolio_id}/transactions`,
6. `GET /portfolios/{portfolio_id}/positions/{security_id}/lots`,
7. `GET /prices/`,
8. `GET /fx-rates/`,
9. `GET /instruments/`,
10. `GET /lookups/instruments`.

### Existing source-data products

The current RFC-0083 source-data product catalog already provides useful DPM ingredients:

| Need | Existing product | Route | Current assessment |
| --- | --- | --- | --- |
| Portfolio state | `PortfolioStateSnapshot:v1` | `/integration/portfolios/{portfolio_id}/core-snapshot` | Use as the governed preferred state source where its sections are sufficient. |
| Holdings and cash | `HoldingsAsOf:v1` | `/portfolios/{portfolio_id}/positions`, `/cash-balances` | Use for operational state and gap filling. |
| Transaction/tax evidence | `TransactionLedgerWindow:v1` plus lot drill-down | `/transactions`, `/positions/{security_id}/lots` | Partial. Per-security tax-lot access is too chatty for production DPM. |
| Instrument enrichment | `InstrumentReferenceBundle:v1` | `/integration/instruments/enrichment-bulk`, `/classification-taxonomy` | Useful, but lacks DPM eligibility, restriction, and settlement profile semantics. |
| Market data | Operational `GET /prices/`, `GET /fx-rates/` | query plane | Usable, but not a governed bulk target-universe market-data product. |
| Readiness/evidence | `DataQualityCoverageReport`, `IngestionEvidenceBundle`, readiness routes | control plane | Useful, but not DPM-specific completeness across model, shelf, tax lots, prices, and FX. |

### Existing pattern in lotus-advise

`lotus-advise` resolves stateful context by composing multiple `lotus-core` routes:

1. query-plane portfolio, positions, cash, prices, FX, and instruments,
2. control-plane enrichment and classification taxonomy,
3. a separate control-plane execution endpoint for advisory simulation execution.

`lotus-manage` should follow the same source-composition pattern, except DPM execution remains in
`lotus-manage`.

## Critical Review And Tightening Decisions

The first draft correctly rejected a monolithic DPM context endpoint, but it was not yet strong
enough as an implementation guide. This gold-standard revision tightens the RFC in these ways:

1. **Architecture boundary:** `lotus-core` owns source-data products, ingestion, materialization,
   lineage, readiness, and trust evidence. `lotus-manage` owns discretionary portfolio-management
   execution, rebalance analysis, workflow, action registers, and portfolio-manager decisions.
2. **Serving-plane clarity:** all new DPM source APIs are control-plane integration products unless
   explicitly retained as existing operational reads. Bulk tax lots, model targets, mandate binding,
   eligibility, prices, and FX are not ad hoc query convenience endpoints.
3. **No local truth in manage:** missing model, mandate, eligibility, shelf, price, FX, or tax-lot
   data must be surfaced through source supportability, not filled by `lotus-manage` heuristics.
4. **Implementation sequencing:** platform automation/scaffolding gaps are handled first so every
   later endpoint starts from the governed baseline rather than repeating local patterns.
5. **Canonical proof:** the front-office canonical stack must include a seeded discretionary mandate
   portfolio with the full DPM source-data set before final proof can be claimed.
6. **Documentation discipline:** repo docs describe implementation and operator runbooks; wiki
   source carries long-lived product, demo, business, and operational material after features are
   real. Aspirational product claims stay in RFC scope until implemented.
7. **Certification standard:** every new endpoint must pass endpoint certification, OpenAPI quality,
   route-family, source-data-product, domain-product, observability, error handling, and live proof
   expectations before the slice is closed.
8. **Single product specification:** the implementation product list is guarded in
   `docs/standards/rfc-087-dpm-source-product-spec.v1.json` so endpoint slices use one
   machine-readable source for product names, routes, ingestion dependencies, certification
   controls, and slice alignment.

The implementation must not start until this RFC is reviewed as the authoritative delivery guide
for `lotus-core` work required to unblock `lotus-manage` RFC-0036.

## Target Architecture

### Core upstream sourcing responsibilities

`lotus-core` remains the canonical source-data product producer. It may receive data from multiple
upstream enterprise systems, but downstream services should see governed Lotus products rather than
raw upstream shapes.

| Source domain | Typical upstream owner | Core responsibility | DPM relevance |
| --- | --- | --- | --- |
| Portfolio, account, positions, and cash | portfolio book of record, custody, accounting platform | Ingest, validate, reconcile, materialize, and expose portfolio state, cash, and holdings. | Required for stateful DPM starting state and cash constraints. |
| Transactions, lots, and cost basis | order/accounting platform, tax-lot engine, custody tax lot feed where applicable | Maintain transaction ledger and position lot state with lineage, restatement, and reconciliation evidence. | Required for tax-aware sells, realized-gain constraints, and audit-grade disposal evidence. |
| Model portfolios and targets | investment office model portfolio system | Ingest effective-dated model definitions, versions, approvals, target weights, bands, and source evidence. | Required for target allocation, drift, and rebalance computation. |
| Mandate, client, and policy binding | mandate administration, CRM/client master, investment policy engine | Ingest effective-dated portfolio-to-mandate/model/policy relationships and authority status. | Required to prove discretionary authority, policy pack selection, and jurisdiction/booking constraints. |
| Product shelf, restrictions, and settlement profile | product master, compliance restriction service, settlement calendar/master data | Ingest or materialize effective eligibility, restriction reason codes, buy/sell flags, settlement days, and calendars. | Required to prevent ineligible buys, explain exclusions, and model settlement-aware execution. |
| Instrument reference and taxonomy | security master, taxonomy/master data platform | Continue publishing enrichment and classification products, adding only DPM-specific fields where they belong to instrument eligibility. | Required for asset-class controls, issuer concentration, liquidity checks, and reporting labels. |
| Prices and FX | market-data vendor, pricing service, internal valuation service | Ingest and expose bounded bulk coverage products with freshness and missing-data diagnostics. | Required for target-universe valuation, drift, cash conversion, and supportability. |

Core must not source discretionary recommendations, rebalance actions, workflow approval decisions,
or proposal status. Those remain `lotus-manage` domain responsibilities.

### Logical flow

```mermaid
flowchart LR
    Manage[lotus-manage DPM source assembler]
    Query[core-query operational reads]
    Control[core-control source products]
    Ingest[core ingestion pipelines]
    Mesh[domain product + trust telemetry]

    Ingest --> Query
    Ingest --> Control
    Query --> Manage
    Control --> Manage
    Query --> Mesh
    Control --> Mesh
    Manage --> Runs[lotus-manage simulate/analyze/async analyze]
```

### Source composition in lotus-manage

`lotus-manage` should compose these source families:

1. portfolio state:
   - primary: `PortfolioStateSnapshot:v1`,
   - fallback/augmentation: `HoldingsAsOf:v1`.
2. model target:
   - new `DpmModelPortfolioTarget:v1`.
3. mandate and model binding:
   - new `DiscretionaryMandateBinding:v1`.
4. instrument eligibility, restriction, and settlement profile:
   - enhanced `InstrumentReferenceBundle:v1` or new `InstrumentEligibilityProfile:v1`.
5. market data for held and target instruments:
   - new `MarketDataCoverageWindow:v1` or enhanced bulk price/FX integration product.
6. tax lots:
   - new `PortfolioTaxLotWindow:v1`.
7. supportability and lineage:
   - existing readiness/lineage routes plus new DPM coverage fields.

### Target `lotus-manage` source call plan

The intended stateful `lotus-manage` integration should be bounded and parallelizable:

1. call `PortfolioStateSnapshot:v1` for portfolio state, holdings, and cash,
2. call `DiscretionaryMandateBinding:v1` to resolve model, policy, jurisdiction, and authority,
3. call `DpmModelPortfolioTarget:v1` using the resolved model and mandate context,
4. call `InstrumentEligibilityProfile:v1` once for the union of held and target instruments,
5. call `MarketDataCoverageWindow:v1` for required prices and FX,
6. call `PortfolioTaxLotWindow:v1` only when tax-aware mode is requested or required by mandate,
7. call readiness/lineage support routes for operator evidence and degraded-state explanation.

`lotus-manage` should not loop over every position for tax lots, prices, FX, enrichment, or
eligibility in production paths once these source products are available.

### Canonical front-office mandate portfolio seed

Before final proof, the governed front-office canonical stack must seed at least one discretionary
mandate portfolio with complete DPM source data. The preferred canonical identity is
`PB_SG_GLOBAL_BAL_001` unless platform RFC-0076 contracts are updated to name a different managed
mandate portfolio.

The seed must include:

1. portfolio, account, base currency, booking center, jurisdiction, and tenant metadata,
2. current holdings, cash balances, cash accounts, and valuation state,
3. transaction and tax-lot/cost-basis history sufficient for tax-aware sells,
4. a discretionary mandate binding with active authority status, model portfolio id, policy pack,
   risk profile, rebalance frequency, rebalance bands, tax-awareness flag, and settlement-awareness
   flag,
5. an approved model portfolio version with target weights, min/max bands, target roles, approval
   status, effective date, and source evidence,
6. instrument enrichment for all held and target instruments,
7. instrument eligibility, product shelf status, restriction reason codes, buy/sell flags,
   settlement days, settlement calendar, liquidity tier, issuer, and ultimate parent issuer,
8. prices for all held and target instruments as of the governed validation date,
9. FX rates for every required cash, local, target, and portfolio currency pair,
10. readiness, lineage, trust telemetry, and data-quality evidence for every DPM source family.

Front-office canonical validation must not claim DPM stateful readiness until this seeded portfolio
can drive live `lotus-core` source APIs and downstream `lotus-manage` source assembly without
fixture-only shortcuts.

## Product Gap Matrix

| DPM data requirement | Current core support | Gap | Target product/API |
| --- | --- | --- | --- |
| Portfolio id, base currency, status | `GET /portfolios/{portfolio_id}` and `core-snapshot` | Sufficient for first integration; ensure metadata fields are complete | No new endpoint required |
| Holdings and cash as of date | `core-snapshot`, `positions`, `cash-balances` | Sufficient for first integration; ensure lineage and data-quality are consumed | No new endpoint required |
| Model portfolio targets | No governed model-target product found | Blocking gap | Add `DpmModelPortfolioTarget:v1` |
| Mandate-to-model binding | Portfolio DTO has mandate-like fields; benchmark assignment has `policy_pack_id`; no governed DPM mandate binding | Blocking gap | Add `DiscretionaryMandateBinding:v1` |
| Policy-pack selector | Some policy ids exist in benchmark assignment/reference records | No DPM policy selector source product | Add to `DiscretionaryMandateBinding:v1` |
| Product shelf status | Instrument enrichment has issuer/liquidity fields; advisory simulation models contain shelf semantics but not source-data product | Blocking gap for DPM buy/sell eligibility | Add `InstrumentEligibilityProfile:v1` |
| Restriction reason codes | Not exposed as governed source data | Blocking gap for audit-grade exclusions | Add to `InstrumentEligibilityProfile:v1` |
| Settlement days/profile | Transaction/cash-account settlement fields exist; instrument-level settlement profile is not exposed | Blocking gap for settlement-aware DPM | Add to `InstrumentEligibilityProfile:v1` or `SettlementProfile:v1` if it grows beyond instrument scope |
| Held instrument prices | `GET /prices/` per security | Usable but chatty; no DPM coverage summary | Enhance with bulk market-data product |
| Target instrument prices | `GET /prices/` per security | Usable but chatty; must cover instruments not currently held | Enhance with bulk market-data product |
| FX for portfolio/cash/target currencies | `GET /fx-rates/` per pair | Usable but chatty; no coverage summary | Enhance with bulk FX coverage product |
| Tax lots | `GET /positions/{security_id}/lots` per security | Too chatty; lacks portfolio-window support | Add `PortfolioTaxLotWindow:v1` |
| Completeness/readiness | `GET /support/portfolios/{portfolio_id}/readiness` | Strong general readiness, not DPM-specific | Enhance readiness with DPM source family coverage |
| Source lineage | `lineage` and product metadata | Needs DPM source family lineage grouping | Enhance product metadata/trust telemetry |

## New And Enhanced Core Products

### 1. `DpmModelPortfolioTarget:v1`

Purpose:

Publish effective model-portfolio target weights for a given model, mandate, tenant, booking
center, and as-of date.

Proposed API:

`POST /integration/model-portfolios/{model_portfolio_id}/targets`

Request fields:

1. `as_of_date`,
2. `tenant_id`,
3. `booking_center_code`,
4. `mandate_id`,
5. optional `portfolio_id`,
6. optional `include_inactive_targets=false`.

Response fields:

1. source-data product envelope fields,
2. `model_portfolio_id`,
3. `model_portfolio_version`,
4. `as_of_date`,
5. `base_currency`,
6. `targets[]` with `instrument_id`, `target_weight`, optional `min_weight`, `max_weight`,
   `target_role`, and `rebalance_band`,
7. `policy_context` with source policy and approval status,
8. `supportability` with `state`, `reason`, `freshness_bucket`, and missing data families.

Required ingestion:

1. `POST /ingest/model-portfolios`,
2. `POST /ingest/model-portfolio-targets`.

Storage requirements:

1. model master table,
2. target version/effective-date table,
3. source-system, source-record-id, source-batch, restatement, approval, and evidence timestamps.

### 2. `DiscretionaryMandateBinding:v1`

Purpose:

Publish the effective DPM binding from portfolio/mandate to model, policy pack, jurisdiction,
booking center, and rebalance constraints.

Proposed API:

`POST /integration/portfolios/{portfolio_id}/mandate-binding`

Request fields:

1. `as_of_date`,
2. `tenant_id`,
3. optional `mandate_id`,
4. optional `booking_center_code`,
5. optional `include_policy_pack=true`.

Response fields:

1. source-data product envelope fields,
2. `portfolio_id`,
3. `mandate_id`,
4. `mandate_type`,
5. `discretionary_authority_status`,
6. `booking_center_code`,
7. `jurisdiction_code`,
8. `model_portfolio_id`,
9. `policy_pack_id`,
10. `risk_profile`,
11. `investment_horizon`,
12. `leverage_allowed`,
13. `tax_awareness_allowed`,
14. `settlement_awareness_required`,
15. `rebalance_frequency`,
16. `rebalance_bands`,
17. `source_lineage`.

Required ingestion:

1. enhance `POST /ingest/portfolios` where existing fields are enough,
2. add `POST /ingest/mandate-bindings` for effective-dated mandate/model/policy relationships.

Storage requirements:

1. effective-dated mandate binding table,
2. policy selector metadata,
3. source lineage and restatement fields.

### 3. `InstrumentEligibilityProfile:v1`

Purpose:

Publish DPM-safe instrument shelf, eligibility, restriction, settlement, and liquidity metadata for
held and target instruments.

Proposed API:

`POST /integration/instruments/eligibility-bulk`

Request fields:

1. `as_of_date`,
2. `tenant_id`,
3. `booking_center_code`,
4. optional `mandate_id`,
5. optional `policy_pack_id`,
6. `instrument_ids[]`.

Response fields:

1. source-data product envelope fields,
2. `records[]` preserving request order,
3. `instrument_id`,
4. `eligibility_status` with values such as `APPROVED`, `RESTRICTED`, `SELL_ONLY`, `BANNED`,
   `SUSPENDED`, `UNKNOWN`,
5. `restriction_reason_codes[]`,
6. `eligible_for_buy`,
7. `eligible_for_sell`,
8. `asset_class`,
9. `product_type`,
10. `issuer_id`,
11. `ultimate_parent_issuer_id`,
12. `liquidity_tier`,
13. `settlement_days`,
14. `settlement_calendar_id`,
15. `source_lineage`,
16. per-record `supportability`.

Required ingestion:

1. enhance `POST /ingest/instruments` only for stable master fields,
2. add `POST /ingest/instrument-eligibility` for policy/mandate/effective-dated eligibility,
3. add or enhance `POST /ingest/reference/classification-taxonomy` only for taxonomy labels, not
   DPM eligibility status.

Storage requirements:

1. effective-dated instrument eligibility table,
2. restriction reason code table or JSON field with governed vocabulary,
3. settlement profile fields,
4. source lineage and evidence timestamps.

### 4. `PortfolioTaxLotWindow:v1`

Purpose:

Publish tax-lot and cost-basis state for all or selected securities in a portfolio over an as-of
scope without requiring one request per security.

Proposed API:

`POST /integration/portfolios/{portfolio_id}/tax-lots`

Request fields:

1. `as_of_date`,
2. optional `security_ids[]`,
3. optional `lot_status_filter`,
4. optional `include_closed_lots=false`,
5. `page_size`,
6. `cursor`.

Response fields:

1. source-data product envelope fields,
2. `portfolio_id`,
3. `as_of_date`,
4. `lots[]`,
5. `security_id`,
6. `lot_id`,
7. `open_quantity`,
8. `acquisition_date`,
9. `cost_basis_base`,
10. `cost_basis_local`,
11. `local_currency`,
12. `tax_lot_status`,
13. `source_transaction_id`,
14. `source_lineage`,
15. paging fields.

Required ingestion:

No new ingestion path is required for first implementation if the existing BUY/cost-basis pipeline
is authoritative. If external tax-lot feeds become source of record, add
`POST /ingest/tax-lots` as a later slice with reconciliation controls.

Storage requirements:

Use existing `position_lot_state` as the initial authority, adding only fields that are proven
missing for DPM tax-aware allocation.

### 5. `MarketDataCoverageWindow:v1`

Purpose:

Publish prices and FX for a caller-provided universe with explicit completeness diagnostics. This
product prevents `lotus-manage` from issuing N price and M FX calls and independently inferring
source coverage.

Proposed APIs:

1. `POST /integration/market-data/prices-bulk`,
2. `POST /integration/market-data/fx-bulk`,
3. optional combined coverage route
   `POST /integration/market-data/coverage`.

Request fields:

1. `as_of_date`,
2. `instrument_ids[]` for prices,
3. `currency_pairs[]` for FX,
4. `valuation_currency`,
5. `freshness_policy`,
6. paging fields when needed.

Response fields:

1. source-data product envelope fields,
2. price records with `instrument_id`, `price_date`, `price`, `currency`, `quality_status`,
3. FX records with `from_currency`, `to_currency`, `rate_date`, `rate`, `quote_convention`,
   `quality_status`,
4. `coverage` with expected count, observed count, missing instruments, missing currency pairs,
   stale rows, and freshness bucket,
5. source lineage and supportability.

Required ingestion:

Existing `POST /ingest/market-prices` and `POST /ingest/fx-rates` are sufficient for first
implementation. They may need stricter source-batch and evidence propagation into response metadata.

## Product Catalog Updates

Add these products to `portfolio_common.source_data_products.SOURCE_DATA_PRODUCT_CATALOG` and
`contracts/domain-data-products/lotus-core-products.v1.json`:

1. `DpmModelPortfolioTarget:v1`,
2. `DiscretionaryMandateBinding:v1`,
3. `InstrumentEligibilityProfile:v1`,
4. `PortfolioTaxLotWindow:v1`,
5. `MarketDataCoverageWindow:v1`.

Each product must define:

1. owner `lotus-core`,
2. consumers including `lotus-manage` and any already known downstream consumers,
3. serving plane,
4. route family,
5. paging/export posture,
6. required metadata fields,
7. source-data security profile,
8. trust telemetry requirements.

## Supported Features Ledger

This RFC must maintain a supported-features list throughout implementation. Items remain
`Planned` until backed by implemented APIs, tests, OpenAPI, data-product metadata, and live
evidence.

| Feature | Status at RFC approval | Implementation-backed when |
| --- | --- | --- |
| Composed DPM source-data architecture with no monolithic context endpoint | Planned | RFC-0036 and core docs reference composed products, and no route or doc claims one all-in-one source endpoint. |
| DPM source-data governance scaffold | Planned | Planned products, domain-product declarations, source-security profiles, route-family posture, and validation evidence exist before runtime routes are exposed. |
| Governed model portfolio target source product | Implemented pending live proof | Ingestion, persistence, API, catalog metadata, OpenAPI, tests, canonical seed data, and local evidence exist; live canonical stack proof remains pending until the refreshed runtime is available. |
| Governed discretionary mandate binding source product | Implemented pending live proof | Ingestion, persistence, API, catalog metadata, OpenAPI, tests, canonical seed data, and local evidence exist; live canonical stack proof remains pending until the refreshed runtime is available. |
| Governed instrument eligibility and settlement profile source product | Implemented pending live proof | Ingestion, persistence, API, catalog metadata, OpenAPI, tests, canonical seed data, and local evidence exist; live canonical stack proof remains pending until the refreshed runtime is available. |
| Bulk portfolio tax-lot source product | Implemented pending live proof | Portfolio-window lot API replaces production per-security fan-out for tax-aware DPM source assembly; local API, catalog, OpenAPI, paging, supportability, and contract evidence exist. Live canonical stack proof remains pending until the refreshed runtime is available. |
| Bulk market-data and FX coverage products | Implemented pending live proof | Held and target universe prices/FX coverage can be fetched with one bounded call; local API, catalog, OpenAPI, supportability, stale/missing diagnostics, and contract evidence exist. Live canonical stack proof remains pending until the refreshed runtime is available. |
| DPM source readiness and supportability | Implemented pending live proof | `DpmSourceReadiness:v1` exposes operator-grade source-family supportability for mandate, model target, eligibility, tax-lot, and market-data readiness; live canonical stack proof remains pending until the refreshed runtime is available. |
| Canonical seeded managed mandate portfolio | Partially implemented pending live proof | Front-office seed includes model target, mandate binding, eligibility, tax-lot, market-price, and FX inputs for `PB_SG_GLOBAL_BAL_001`; live canonical runtime proof is blocked until core-control is reachable with this branch. |
| API certification and Swagger quality for all DPM source APIs | Planned | Each endpoint is certified with complete descriptions, examples, errors, extensions, and tests. |
| Wiki and demo-ready product material | Implemented pending publication | Repo-local wiki source describes implemented DPM source products with diagrams, current proof posture, and audience-specific guidance; GitHub wiki publication follows merge. |

The final closure slice must update this ledger to distinguish `Implemented`, `Deferred`, and
`Rejected` items. Any deferred item must include a reason, owner, follow-up issue or RFC, and impact
on `lotus-manage` RFC-0036.

## Route Family Classification

| Route | Family | Serving plane | Reason |
| --- | --- | --- | --- |
| `/integration/model-portfolios/{model_portfolio_id}/targets` | Analytics Input | `query_control_plane_service` | Deterministic downstream target input, not an operational portfolio read. |
| `/integration/portfolios/{portfolio_id}/mandate-binding` | Analytics Input | `query_control_plane_service` | DPM policy/source selector required by downstream execution input assembly. |
| `/integration/instruments/eligibility-bulk` | Analytics Input | `query_control_plane_service` | Governed source input for DPM eligibility and downstream analytics/suitability. |
| `/integration/portfolios/{portfolio_id}/tax-lots` | Analytics Input | `query_control_plane_service` | Productized bulk tax-lot window for DPM source assembly with paging and supportability; existing per-security lot reads remain operational reads. |
| `/integration/market-data/prices-bulk` | Analytics Input | `query_control_plane_service` | Bulk market-data window with coverage diagnostics. |
| `/integration/portfolios/{portfolio_id}/dpm-source-readiness` | Control Plane And Policy | `query_control_plane_service` | Operator-grade supportability summary used to decide whether stateful DPM source assembly can be promoted. |
| `/integration/market-data/fx-bulk` | Analytics Input | `query_control_plane_service` | Bulk FX window with coverage diagnostics. |
| `/integration/market-data/coverage` | Control-Plane And Policy | `query_control_plane_service` | Coverage/readiness evidence. |

Final implementation must update `docs/standards/route-contract-family-registry.json` and pass
`make route-contract-family-guard`.

## Data Mesh Requirements

Every new product must meet the current Lotus mesh baseline:

1. repo-native producer declaration in `contracts/domain-data-products/lotus-core-products.v1.json`,
2. platform vocabulary alignment for product names, identifiers, and trust metadata,
3. `x-lotus-source-data-product` OpenAPI metadata,
4. `x-lotus-source-data-security` OpenAPI metadata,
5. runtime DTO envelope fields:
   - `product_name`,
   - `product_version`,
   - `tenant_id`,
   - `generated_at`,
   - `as_of_date`,
   - `restatement_version`,
   - `reconciliation_status`,
   - `data_quality_status`,
   - `latest_evidence_timestamp`,
   - `source_batch_fingerprint`,
   - `snapshot_id`,
   - `policy_version`,
   - `correlation_id`.
6. trust telemetry fixture under `contracts/trust-telemetry/`,
7. runtime collection path or explicit static-fixture fallback with no overclaiming,
8. validation through:
   - `make source-data-product-contract-guard`,
   - `make domain-product-validate`,
   - trust telemetry tests,
   - OpenAPI/vocabulary gates.

## Observability, Logging, And Supportability

Each new or enhanced endpoint must provide:

1. structured logs with `correlation_id`, `trace_id`, product name, route family, and bounded
   outcome labels,
2. no portfolio id, security id, transaction id, request body, response body, or client-sensitive
   identifiers as Prometheus labels,
3. bounded counters for request outcome, data-quality status, and supportability state,
4. histograms for endpoint latency where existing platform patterns support them,
5. supportability objects with `state`, `reason`, `freshness_bucket`, and missing source families,
6. readiness diagnostics for DPM source families through either:
   - enhanced `/support/portfolios/{portfolio_id}/readiness`, or
   - a focused `/support/portfolios/{portfolio_id}/dpm-readiness` route if the generic readiness
     contract becomes too broad.

## Security And Access Requirements

Each product must:

1. be tenant scoped,
2. carry entitlement/capability rules derived from source-data product catalog metadata,
3. honor existing enterprise readiness middleware,
4. require policy headers where configured,
5. emit audit events according to the product access class,
6. classify sensitivity and retention posture in the source-data security profile,
7. avoid leaking restriction rationale or mandate metadata beyond entitled consumers.

## API Documentation Requirements

Swagger/OpenAPI for every route must include:

1. clear `What`, `How`, and `When` operation descriptions,
2. explicit `When not to use` guidance where there is a risk of wrong-layer consumption,
3. examples for every request and success response,
4. JSON examples for every error response,
5. descriptions, types, and examples for every attribute,
6. route grouping aligned with RFC-0082 families,
7. source-data product and security OpenAPI extensions,
8. pagination and ordering semantics where applicable,
9. supportability and data-quality behavior.

## Performance And Latency Requirements

This RFC exists partly to prevent high-latency fan-out from `lotus-manage`.

Targets:

1. `lotus-manage` should be able to assemble one DPM stateful context with bounded parallel calls,
   not per-position/per-currency serial loops.
2. Bulk endpoints must preserve deterministic ordering and page safely.
3. Tax-lot, price, and FX retrieval must have request-size limits and clear paging/export posture.
4. Query plans for effective-dated model, mandate, eligibility, and market data must be covered by
   repository or integration tests where practical.
5. Load and latency gates must include at least one canonical `PB_SG_GLOBAL_BAL_001` stateful DPM
   source assembly proof once implementation reaches live runtime.

## Delivery Slices

Each slice must be implemented, validated, reviewed, committed, and pushed before moving to the
next. If a later slice reveals a platform or scaffolding gap that should be solved centrally, return
to the platform automation slice and fix it there rather than normalizing local one-off code.

### Slice 0 - RFC approval, inventory, and rebaseline

Scope:

1. Confirm existing `core-control` and `core-query` OpenAPI routes, source-data products,
   ingestion endpoints, and route-family metadata.
2. Confirm `lotus-advise` source-composition pattern and document which parts are reusable for
   `lotus-manage`.
3. Rebaseline `lotus-manage` RFC-0036 so it references composed core source products and no longer
   expects a single DPM context route.
4. Close, update, or create issues for any docs, code, or downstream consumers that still reference
   a monolithic `dpm-execution-context` route.
5. Review this RFC for implementation readiness before any code implementation begins.

Exit evidence:

1. RFC-087 merged or explicitly approved as the active implementation guide,
2. existing route/product inventory attached to the RFC or companion evidence
   (`docs/RFCs/RFC-087-slice-0-inventory-and-rebaseline-evidence.md`),
3. `lotus-manage` RFC-0036 has the correct composed-source dependency model,
4. no active docs claim that `lotus-core` should expose one all-in-one DPM context endpoint.

### Slice 1 - Platform automation and scaffolding improvement

Scope:

1. Identify gaps in `lotus-platform` automation that should be scaffolded for new apps and source
   products by default.
2. Improve platform automation rather than solving repeatable concerns locally in `lotus-core`.
3. Ensure scaffolding covers, where applicable:
   - API certification pattern,
   - Swagger/OpenAPI quality requirements,
   - source-data product catalog declarations,
   - route-family registry entries,
   - source-data security metadata,
   - trust telemetry fixtures,
   - structured logging,
   - no-sensitive-metric-label checks,
   - health/readiness endpoint conventions,
   - error response models,
   - test scaffolding,
   - CI defaults,
   - documentation and wiki source skeletons,
   - governance hooks for mesh, vocabulary, and no-alias validation.
4. Add or update platform scaffolding tests so future apps begin under the same governance baseline.
5. Document any platform limitation that cannot be improved in this RFC and create a follow-up
   issue with owner, impact, and acceptance criteria.

Exit evidence:

1. platform automation changes are committed in the appropriate `lotus-platform` branch or linked
   as a prerequisite PR,
2. new scaffolding can produce or validate the baseline artifacts needed by the DPM source products,
3. platform automation tests pass,
4. RFC-087 implementation no longer relies on avoidable local boilerplate,
5. Slice evidence is recorded in
   `docs/RFCs/RFC-087-slice-1-platform-scaffold-evidence.md`.

### Slice 2 - Cleanup and structure

Scope:

1. Remove dead, duplicate, misleading, or advisory-leftover code in core areas touched by DPM source
   products.
2. Improve repository structure only where it materially improves source-data product clarity,
   modularity, testability, or future endpoint additions.
3. Reduce documentation sprawl:
   - keep implementation details, RFC execution notes, and developer commands in repo docs,
   - move long-lived product, operator, sales/demo, and business-friendly material to repo-local
     wiki source when it becomes implementation-backed,
   - avoid duplicating the same narrative in README, docs, and wiki.
4. Keep source-data product, route-family, domain-product, and supported-feature lists aligned.
5. Verify that no stale docs describe unsupported DPM APIs or stateful behavior.

Exit evidence:

1. focused cleanup diff with no unrelated churn,
2. stale references removed or explicitly dispositioned,
3. wiki source is updated where current implementation truth changed, or a deliberate no-wiki-change
   decision is recorded,
4. repository docs and RFC index remain navigable and non-duplicative,
5. DPM source-product implementation structure is guarded by
   `docs/standards/rfc-087-dpm-source-product-spec.v1.json`,
6. Slice evidence is recorded in
   `docs/RFCs/RFC-087-slice-2-cleanup-structure-evidence.md`.

### Slice 3 - Product catalog, route-family, and governance scaffolding

Scope:

1. Add planned products to `source_data_products.py`.
2. Add source-data security profiles.
3. Add route-family posture according to local guard conventions. Planned routes must not be
   added to the active route-family registry until the router exists and is tested.
4. Add repo-native producer declarations and trust telemetry placeholders.
5. Add supported-features entries with `Planned` status only.
6. Add tests that prevent product-name, route-family, OpenAPI-extension, source-security, and
   metadata drift.

Exit evidence:

1. `make source-data-product-contract-guard` passes,
2. `make route-contract-family-guard` passes,
3. `make domain-product-validate` passes when platform sibling checkout is available,
4. no new endpoint is exposed before the catalog and governance scaffolding is in place,
5. completed evidence is recorded in
   `docs/RFCs/RFC-087-slice-3-governance-scaffold-evidence.md`.

### Slice 4 - Model portfolio target pipeline and API

Scope:

1. Add model portfolio and target ingestion DTOs/routes.
2. Add persistence tables and migrations for model master, target versions, target rows, source
   evidence, approval state, and restatement lineage.
3. Add an effective-dated resolver service.
4. Add `POST /integration/model-portfolios/{model_portfolio_id}/targets`.
5. Add complete OpenAPI, source-data metadata, errors, telemetry, and tests.
6. Seed canonical model portfolio data for the front-office managed mandate portfolio.

Exit evidence:

1. API returns deterministic target weights for canonical data,
2. target weights validate to expected tolerances and preserve ordering,
3. missing, stale, unapproved, and overlapping-effective-date model data are source-safe and tested,
4. `lotus-manage` can consume the product in a mocked integration test.

Current implementation evidence:

1. `DpmModelPortfolioTarget:v1` is active in the source-data catalog, source-security profile,
   route-family registry, and repo-native domain-product declaration.
2. Model portfolio definition and target ingestion routes, persistence, resolver, and control-plane
   API are implemented.
3. The canonical front-office seed now publishes `MODEL_PB_SG_GLOBAL_BAL_DPM` version `2026.04`
   with target weights summing to `1.0000000000`.
4. Local proof is recorded in
   `docs/RFCs/RFC-087-slice-4-model-portfolio-target-evidence.md`.
5. Live canonical stack proof remains pending until the running stack is refreshed with this
   branch.

### Slice 5 - Discretionary mandate binding pipeline and API

Scope:

1. Add or enhance portfolio/mandate ingestion for DPM binding fields.
2. Add effective-dated mandate binding persistence.
3. Add `POST /integration/portfolios/{portfolio_id}/mandate-binding`.
4. Include policy pack selector, model binding, authority status, jurisdiction, booking center,
   risk profile, tax and settlement flags, rebalance frequency, bands, and source lineage.
5. Seed canonical mandate binding data for the front-office managed mandate portfolio.

Exit evidence:

1. canonical portfolio resolves mandate, model, and policy selectors,
2. inactive, unauthorized, missing, ambiguous, or future-dated mandate states are source-safe and
   tested,
3. `lotus-manage` does not infer mandate truth locally,
4. OpenAPI examples clearly explain when to use and when not to use this endpoint.

Current implementation evidence:

1. `DiscretionaryMandateBinding:v1` is active in the source-data catalog, source-security profile,
   route-family registry, and repo-native domain-product declaration.
2. Mandate binding ingestion, persistence, effective-dated resolver, and control-plane API are
   implemented.
3. The canonical front-office seed now publishes `MANDATE_PB_SG_GLOBAL_BAL_001` for
   `PB_SG_GLOBAL_BAL_001`, binding it to `MODEL_PB_SG_GLOBAL_BAL_DPM` and
   `POLICY_DPM_SG_BALANCED_V1`.
4. Local proof is recorded in
   `docs/RFCs/RFC-087-slice-5-discretionary-mandate-binding-evidence.md`.
5. Live canonical stack proof remains pending until the running stack is refreshed with this
   branch.

### Slice 6 - Instrument eligibility, restrictions, and settlement pipeline and API

Scope:

1. Add eligibility/restriction ingestion.
2. Add effective-dated eligibility storage.
3. Add `POST /integration/instruments/eligibility-bulk`.
4. Preserve request order and explicit unknown records.
5. Include settlement days/calendar, restriction reason codes, buy/sell flags, product shelf
   status, issuer, parent issuer, liquidity tier, supportability, and source lineage.
6. Seed canonical eligibility data for every held and target instrument in the managed mandate
   portfolio.

Exit evidence:

1. held and target instruments return deterministic eligibility,
2. missing eligibility produces bounded supportability rather than local fallback truth,
3. DPM shelf construction can be proven without advisory-era assumptions,
4. sensitive restriction rationale is protected by source-data security and capability rules.

Current implementation evidence:

1. `InstrumentEligibilityProfile:v1` is active in the source-data catalog, source-security profile,
   route-family registry, and repo-native domain-product declaration.
2. Instrument eligibility ingestion, persistence, effective-dated resolver, and control-plane bulk
   API are implemented.
3. The canonical front-office seed now publishes eligibility profiles for every held and model
   target instrument in `PB_SG_GLOBAL_BAL_001`, including an explicit restricted private-credit
   instrument for supportability and explainability proof.
4. The bulk API preserves request order and returns explicit `UNKNOWN` records for missing
   eligibility instead of allowing downstream local fallback truth.
5. Local proof is recorded in
   `docs/RFCs/RFC-087-slice-6-instrument-eligibility-evidence.md`.
6. Live canonical stack proof remains pending until the running stack is refreshed with this branch.

### Slice 7 - Bulk tax-lot pipeline and API

Scope:

1. Add `POST /integration/portfolios/{portfolio_id}/tax-lots`.
2. Source from existing cost-basis/lot state initially.
3. Add paging, filtering, deterministic ordering, source lineage, data-quality status, and
   supportability.
4. Assess whether external tax-lot ingestion is required; implement only if source-of-record
   requirements demand it.
5. Seed canonical lot/cost-basis data for tax-aware DPM validation.

Exit evidence:

1. tax-aware DPM can resolve all portfolio lots without per-security fan-out,
2. page boundaries are deterministic and tested,
3. empty, incomplete, closed, and stale lots are visible through supportability,
4. query shape and pagination are covered by repository or integration tests.

Current implementation evidence:

1. `PortfolioTaxLotWindow:v1` is active in the source-data catalog, source-security profile,
   route-family registry, and repo-native domain-product declaration.
2. `POST /integration/portfolios/{portfolio_id}/tax-lots` resolves portfolio-window tax lots from
   `position_lot_state`, preserving core as the source of cost-basis and lot lineage.
3. The API supports bounded cursor paging, deterministic ordering by `acquisition_date` and
   `lot_id`, optional security filtering, open/closed status filtering, closed-lot inclusion, source
   lineage, data-quality metadata, and page-scope supportability.
4. Pagination supportability avoids false missing-security claims while more pages remain by
   returning `DEGRADED` with `TAX_LOTS_PAGE_PARTIAL`; missing requested securities are reported as
   `INCOMPLETE` only after the page scope is exhausted.
5. Focused unit, router, OpenAPI, source-data-product, route-family, and domain-product gates pass
   locally. Evidence is recorded in
   `docs/RFCs/RFC-087-slice-7-portfolio-tax-lot-evidence.md`.
6. Live canonical stack proof remains pending until the running stack is refreshed with this branch.

### Slice 8 - Bulk market-data and FX coverage pipeline and APIs

Scope:

1. Add bulk prices and FX integration products or extend existing integration/reference routes
   under the governed market-data product family.
2. Add coverage diagnostics for held and target universe instruments.
3. Preserve source evidence timestamps, observed dates, freshness buckets, missing families, and
   quality status.
4. Seed canonical prices and FX for every held and target instrument/currency pair in the managed
   mandate portfolio.

Exit evidence:

1. DPM target universe prices and FX can be sourced with bounded calls,
2. missing target price/FX cases are deterministic and supportability-visible,
3. request-size limits, paging behavior, and latency-sensitive query paths are tested,
4. `lotus-manage` source assembly no longer needs N price or M FX serial loops.

Current implementation evidence:

1. `MarketDataCoverageWindow:v1` is active in the source-data catalog, source-security profile,
   route-family registry, and repo-native domain-product declaration.
2. `POST /integration/market-data/coverage` resolves latest available instrument prices and FX
   rates on or before `as_of_date` from existing `market_prices` and `fx_rates` source tables.
3. The API supports bounded instrument and FX-pair requests, `valuation_currency`,
   `max_staleness_days`, tenant lineage context, source-data runtime metadata, and supportability
   diagnostics for missing and stale observations.
4. Missing observations return `INCOMPLETE` with `MARKET_DATA_MISSING`; stale-only observations
   return `DEGRADED` with `MARKET_DATA_STALE`; complete fresh coverage returns `READY`.
5. Focused unit, router, OpenAPI, source-data-product, route-family, and domain-product gates pass
   locally. Evidence is recorded in
   `docs/RFCs/RFC-087-slice-8-market-data-coverage-evidence.md`.
6. Live canonical stack proof remains pending until the running stack is refreshed with this branch.

### Slice 9 - DPM source readiness, observability, and supportability

Scope:

1. Enhance portfolio readiness with DPM source-family coverage or add a focused DPM readiness
   route.
2. Include model, mandate, eligibility, tax-lot, price, FX, lineage, and canonical seed
   completeness.
3. Add bounded metrics and no-sensitive-label tests.
4. Add structured logs and error handling that preserve correlation without leaking sensitive
   portfolio, security, mandate, or restriction identifiers as labels.
5. Add operational runbook content for diagnosing ready, partial, stale, and blocked DPM source
   states.

Exit evidence:

1. operators can explain why stateful DPM is ready, partial, stale, or blocked,
2. metrics and logs meet platform observability constraints,
3. no sensitive identifiers leak into metric labels,
4. readiness is covered by unit, integration, and live proof.

### Slice 10 - Canonical front-office managed mandate seed and automation

Scope:

1. Extend canonical front-office automation and seed data so it includes the managed mandate
   portfolio source families listed in this RFC.
2. Ensure seed automation loads portfolio, holdings, cash, transactions, tax lots, model targets,
   mandate binding, eligibility, prices, FX, readiness, lineage, and trust telemetry evidence.
3. Ensure the seed data is industry-plausible for a private-banking discretionary mandate:
   diversified holdings, target weights that sum correctly, realistic bands, sensible cash,
   settlement calendars, tax lots, restricted instruments, and at least one explicit eligibility
   exclusion.
4. Update platform contracts if the canonical managed mandate portfolio identity or invariants
   become durable cross-repo truth.

Exit evidence:

1. front-office canonical stack can seed and validate the managed mandate source dataset,
2. seed invariants catch missing or superficial DPM data,
3. canonical live validation uses real core APIs, not static manage-only fixtures,
4. diagrams and operator evidence identify upstream source families and downstream consumers.

### Slice 11 - Implementation proof

Scope:

1. Prove each implemented endpoint directly against local and live core services.
2. Prove `lotus-manage` source assembly against composed core products.
3. Capture JSON evidence, command output, request/response examples, OpenAPI snapshots, readiness
   evidence, and human-readable summaries.
4. Review evidence critically:
   - compare totals, weights, counts, missing data, stale data, and supportability states,
   - verify every output family, not just headline figures,
   - identify gaps, inconsistencies, weak tests, slow paths, and loose ends.
5. Iterate until the implementation is genuinely complete, not merely demonstrable.

Exit evidence:

1. `lotus-manage` stateful simulate, analyze, and async analyze can be enabled in a controlled
   environment,
2. source lineage ties every DPM source family to core product ids and evidence,
3. local and remote CI gates are green,
4. RFC-0036 can resume final gold-standard implementation.

### Slice 12 - Second-last hardening and review

Scope:

1. Perform a proper code review of the full implementation.
2. Remove remaining dead code, duplicate logic, stale docs, superficial tests, and misleading
   naming.
3. Verify API certification pattern compliance for every new or enhanced endpoint.
4. Verify platform governance and enterprise data mesh standards are met.
5. Ensure all APIs are certified.
6. Ensure Swagger/OpenAPI is high quality:
   - grouped correctly,
   - clear `What`, `When`, `How`, and `When not to use` guidance,
   - full request and response examples,
   - error examples,
   - every attribute has description, type, and example value,
   - source-data product and security extensions are present.
7. Ensure error handling is complete, correct, and properly tested.
8. Run focused performance and latency checks for bounded source assembly.

Exit evidence:

1. endpoint certification records exist for every route,
2. no known high-severity review findings remain,
3. Swagger and API vocabulary gates are green,
4. error and degraded-state behavior is tested,
5. CI and live evidence are current.

### Slice 13 - Final closure

Scope:

1. Update documentation, README, RFC index, supported-features list, and operator runbooks.
2. Update repo-local wiki source with implementation-backed product, business, operator, sales/demo,
   and architecture material, including diagrams for upstreams, core source products, manage
   composition, readiness, and downstream consumers.
3. Run wiki check-only before merge and publish wiki after merge according to the Lotus wiki rule.
4. Update agent context:
   - `REPOSITORY-ENGINEERING-CONTEXT.md` for core-local truth,
   - platform context if the source-product or canonical seed pattern became cross-repo guidance,
   - skill routing or guidance if future agents need a better path.
5. Consciously review whether skills, guidance, documentation, or agent context should be added,
   removed, tightened, or clarified. If no change is needed, record that as a deliberate outcome.
6. Update `lotus-manage` RFC-0036 and supported-features evidence to reflect implemented core
   dependencies.
7. Complete branch hygiene: small commits, pushed branch, PR evidence, resolved CI, no unrelated
   changes, and clean worktree.

Exit evidence:

1. core PR Merge Gate and relevant main-releasability gates are green,
2. downstream `lotus-manage` proof is linked,
3. wiki source and publication status are recorded,
4. supported-features ledger distinguishes implemented, deferred, and rejected scope,
5. branch hygiene is complete.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Recreating a monolithic context endpoint through a different name | Keep each product independently useful, governed, and cataloged; `lotus-manage` owns assembly. |
| Wrong serving plane | Use RFC-0082 family classification before adding each route. |
| High latency from too many calls | Add bulk target-universe products for tax lots, prices, FX, and eligibility. |
| Local DPM fallback becomes hidden source truth | Require source-lineage and supportability fields; missing source data blocks or degrades explicitly. |
| Mesh documentation drifts from implementation | Add catalog, contract, OpenAPI, trust telemetry, and wiki checks in each slice. |
| Mandate/restriction data leaks beyond entitlement | Apply source-data security profiles and capability rules before runtime enablement. |
| New ingestion is under-modeled | Use source batch, idempotency, reconciliation, and evidence patterns from RFC-0083. |
| Canonical proof uses thin or unrealistic seed data | Add managed mandate seed invariants covering holdings, cash, model targets, mandate binding, eligibility, tax lots, prices, FX, readiness, and at least one restriction. |
| Platform automation gaps are repeatedly solved in apps | Require Slice 1 to improve `lotus-platform` scaffolding or record a governed follow-up before app-local work proceeds. |
| Swagger is technically valid but not self-explanatory | Require endpoint certification evidence that reviews operation guidance, every attribute, examples, and error behavior. |
| Live proof passes superficially | Require critical evidence review across totals, weights, counts, lineage, missing data, supportability states, and latency before closure. |

## Dependencies And Sequencing Rules

Implementation order is intentional:

1. Slice 0 and Slice 1 must complete before endpoint implementation.
2. Slice 3 must complete before any DPM source API is exposed.
3. Model target and mandate binding must be available before meaningful stateful `lotus-manage`
   proof can start.
4. Eligibility, tax lots, prices, and FX may be implemented in parallel only if write scopes are
   disjoint and each slice owns its tests, OpenAPI, and evidence.
5. Canonical seed automation must be ready before live end-to-end proof is accepted.
6. Hardening must happen after all endpoint slices and proof slices, not as a substitute for them.
7. Final closure cannot proceed while CI, wiki, supported-features, context, or downstream RFC-0036
   evidence is stale.

Cross-repo dependencies:

1. `lotus-platform`: scaffolding, wiki sync, canonical front-office contracts, CI/governance
   automation, route and data-product validation support.
2. `lotus-manage`: RFC-0036 source assembly changes, endpoint consumption, simulate/analyze proof,
   supported-features updates.
3. `lotus-gateway`: no implementation dependency in this RFC; future gateway integration should
   consume certified `lotus-manage` APIs after RFC-0036 resumes.
4. `lotus-workbench`: no direct UI dependency in this RFC; front-office canonical automation is
   used only for seeded data and live validation evidence.

## Evidence Expectations

Every implementation slice must produce evidence that is specific enough for an independent
reviewer to reproduce or challenge it.

Required evidence classes:

1. local commands with exact command lines and pass/fail outcome,
2. GitHub run id, branch, commit SHA, and check names,
3. endpoint request and response examples for success, validation error, missing data, and degraded
   source-data state,
4. OpenAPI excerpts or generated snapshots proving metadata and examples,
5. data-product catalog and route-family guard output,
6. source-lineage and supportability examples,
7. live canonical proof once deployed behavior changes,
8. wiki/source documentation proof when long-lived product truth changes,
9. issue links for deferred, downstream, or platform follow-up work.

Evidence must explicitly state what was not proven. Do not infer `lotus-manage`, Gateway, Workbench,
or client-demo readiness from core-only tests.

## Validation Plan

Each implementation slice must include:

1. unit tests for DTO validation and resolver edge cases,
2. repository/service tests for query shape and effective dating,
3. route tests for success, missing data, invalid request, paging, and unauthorized/degraded cases,
4. OpenAPI tests for summaries, descriptions, examples, error examples, and extensions,
5. source-data product guard tests,
6. route-family registry guard tests,
7. trust telemetry tests,
8. no-sensitive-metrics tests,
9. focused live proof when the slice changes deployed source-data behavior.
10. supported-features ledger update when a planned product becomes implemented or deferred.

Final validation must include:

1. `make ci-local`,
2. relevant `make ci` or GitHub PR Merge Gate,
3. `make source-data-product-contract-guard`,
4. `make domain-product-validate`,
5. `make route-contract-family-guard`,
6. OpenAPI/vocabulary gates,
7. live core-control and core-query API proof,
8. downstream `lotus-manage` stateful source assembly proof.
9. canonical front-office managed mandate seed validation,
10. wiki check-only before merge,
11. endpoint certification evidence for every new API.

## Acceptance Criteria

This RFC is complete only when:

1. `lotus-core` exposes all missing DPM source products as governed, documented, tested APIs,
2. all products are present in the source-data product catalog and domain-product declarations,
3. ingestion and persistence paths exist for every source-owned data point,
4. supportability and trust telemetry can explain completeness for each DPM source family,
5. `lotus-manage` no longer depends on a monolithic source route,
6. `lotus-manage` proves stateful simulate/analyze/async analyze using composed core products,
7. all relevant CI, mesh, OpenAPI, route-family, and security gates are green,
8. canonical front-office automation seeds and validates a complete managed mandate portfolio,
9. supported-features material reflects only implementation-backed features,
10. wiki/source docs describe implementation-backed current state without aspirational claims,
11. platform automation/scaffolding improvements are implemented or consciously dispositioned,
12. final review records whether agent context, skills, or guidance changed and why.

## Gold-Pass Assessment

Date: 2026-05-02

Assessment decision: first-wave DPM source products are implemented to a strong local and CI-backed
standard, but RFC-087 is not fully closed. Final gold-standard closure remains blocked by live
canonical runtime proof, DPM source-family readiness/supportability publication, downstream
stateful `lotus-manage` proof, and post-merge wiki publication.

### Slice-By-Slice Audit

| Slice | Audit outcome | Evidence and remaining work |
| --- | --- | --- |
| Slice 0 - RFC review and target architecture | Complete | RFC-087 rejects a monolithic DPM context endpoint and defines product-specific core source products consumed by `lotus-manage`. |
| Slice 1 - Platform automation and scaffolding | Partially complete | Existing platform guards cover route families, source-data catalog metadata, domain products, OpenAPI, and wiki checks. The reusable RFC-087 live validator added in this pass should be considered as a candidate pattern for future app scaffolding rather than staying a one-off script forever. |
| Slice 2 - Cleanup and structure | Complete for current source-product scope | First-wave DPM products are no longer in the planned in-code catalog; route metadata, source-security profiles, domain declaration, wiki, and RFC status align with implemented products. |
| Slice 3 - Source inventory and canonical seed contract | Partially complete | Canonical front-office seed includes the managed mandate model, binding, eligibility, tax lots through existing transaction/lot state, prices, and FX inputs. Live proof is blocked while `core-control.dev.lotus` is unreachable. |
| Slice 4 - Model portfolio targets | Complete pending live proof | Ingestion, persistence, API, supportability, source-data metadata, OpenAPI, tests, canonical seed, and manage client integration exist. |
| Slice 5 - Mandate binding | Complete pending live proof | Effective mandate, model, policy, authority, booking center, jurisdiction, tax-awareness, settlement-awareness, and rebalance constraints are modeled and exposed. |
| Slice 6 - Instrument eligibility | Complete pending live proof | Bulk eligibility and restriction sourcing exists with canonical proof data including a restricted private-credit instrument. |
| Slice 7 - Portfolio tax lots | Complete pending live proof | Bulk portfolio-window tax-lot API avoids per-security fan-out and exposes paging/supportability for tax-aware sell allocation. |
| Slice 8 - Market data and FX coverage | Complete pending live proof | Bulk market-data/FX coverage API exposes missing and stale diagnostics for held and target universe validation. |
| Slice 9 - DPM source readiness/supportability | Complete pending live proof | `DpmSourceReadiness:v1` now evaluates mandate, model target, eligibility, tax-lot, and market-data source families with bounded missing/stale diagnostics; live canonical evidence remains pending until the refreshed runtime is reachable. |
| Slice 10 - Managed mandate canonical automation | Partially complete | Seed data exists for source-product validation; canonical live evidence is not captured because the current `core-control.dev.lotus` endpoint refuses connections. |
| Slice 11 - Implementation proof | Partially complete | Local tests, guards, and remote Feature Lane evidence exist. Live canonical evidence is now executable through `make live-dpm-source-validate` but currently fails on runtime availability. |
| Slice 12 - Second-last hardening and review | Not complete | Must run after live proof and readiness are implemented; Swagger and endpoint certification for the five current products are locally covered but still need live deployed review. |
| Slice 13 - Final closure | Not complete | Wiki source is updated in-repo; publication, final supported-features closure, agent context review, downstream `lotus-manage` proof, and branch hygiene remain. |

### What Was Truly Completed

1. Five product-specific DPM source APIs are implemented in `lotus-core`:
   `DpmModelPortfolioTarget:v1`, `DiscretionaryMandateBinding:v1`,
   `InstrumentEligibilityProfile:v1`, `PortfolioTaxLotWindow:v1`, and
   `MarketDataCoverageWindow:v1`.
2. Each product is wired through route metadata, source-data product catalog metadata,
   source-security profiles, domain-product declarations, OpenAPI contract shape, tests, and
   canonical seed data where applicable.
3. `lotus-manage` RFC-0036 now has typed client integration for all five first-wave products and
   remains correctly feature-gated until live source-family readiness is available.
4. A reusable live validator now probes OpenAPI publication and all five source-product routes
   against canonical managed mandate identifiers.

### Quality Improvements Made

1. The architecture now uses independently governed source products instead of a hidden all-in-one
   DPM context route.
2. Bulk eligibility, tax-lot, and market-data requests reduce production fan-out and give clearer
   failure diagnostics.
3. Supportability state, missing/stale diagnostics, product identity, and canonical totals are
   asserted in executable validation instead of relying on prose.
4. Wiki material separates developer API truth, business meaning, operating posture, and
   client-demo readiness.

### Debt Removed

1. The first-wave DPM source products were removed from the planned in-code catalog after
   implementation.
2. The old design assumption that core would expose one composed DPM context route is no longer
   treated as the target state.
3. Prose-only live proof has been replaced with `scripts/validate_live_dpm_source_products.py` and
   `make live-dpm-source-validate`.

### Testing And Evidence

Local validation evidence captured in this audit:

1. `python -m pytest tests/unit/scripts/test_validate_live_dpm_source_products.py -q` passed with
   5 tests.
2. `python -m ruff check scripts/validate_live_dpm_source_products.py tests/unit/scripts/test_validate_live_dpm_source_products.py` passed.
3. `python -m ruff format --check scripts/validate_live_dpm_source_products.py tests/unit/scripts/test_validate_live_dpm_source_products.py` passed.
4. `make source-data-product-contract-guard` passed.
5. `make domain-product-validate` passed.

Remote evidence already available before this audit:

1. `lotus-core` Feature Lane run `25244226940` passed for commit `0cb8cb6a`.
2. `lotus-manage` Feature Lane run `25244329249` passed for commit `b7ce8a1`.

Live evidence captured in this audit:

1. `python scripts/validate_live_dpm_source_products.py --control-base-url http://core-control.dev.lotus --json-output output/rfc-087-gold-pass/live-dpm-source-products.json`
   executed and produced a 6/6 failure summary because `core-control.dev.lotus` refused the
   connection with `[WinError 10061]`.
2. This is not endpoint-level proof or business validation. It is truthful evidence that the
   canonical runtime was not reachable for this branch at audit time.

### Standard Assessment

The implemented first-wave source products are strong enough for continued hardening and downstream
integration work, but the overall RFC has not yet reached final gold standard. The remaining
production-grade blockers are explicit: make the canonical core runtime reachable with this branch,
prove all five source-product routes live with realistic managed mandate data, add or expose
source-family readiness/supportability, prove `lotus-manage` stateful source assembly end to end,
complete endpoint certification against deployed Swagger and live responses, then publish the wiki
after merge.

### Documentation And Skill Review

Documentation required improvement in this audit because the prior wiki/RFC state was accurate for
engineering but not polished enough for business, sales, marketing, operations, and client-demo
reuse. Repo-local wiki source is the authored current-state product material, while RFCs carry
delivery evidence, trade-offs, and closure decisions. No new local agent skill is required yet; the
existing Lotus README/wiki governance skill is sufficient if future contributors keep
business-facing wiki prose distinct from implementation RFC evidence.
