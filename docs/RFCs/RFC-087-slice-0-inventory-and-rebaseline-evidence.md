# RFC-087 Slice 0 Inventory And Rebaseline Evidence

| Field | Value |
| --- | --- |
| RFC | RFC-087 DPM Source Data Products for lotus-manage Stateful Execution |
| Slice | Slice 0 - RFC approval, inventory, and rebaseline |
| Date | 2026-05-02 |
| Core branch | `feat/dpm-source-data-products-rfc` |
| Core commit baseline | `df9b3b55` |
| Manage branch reviewed | `feat/lotus-manage-dpm-scope-cleanup` |
| Scope | Inventory and architecture rebaseline only; no core runtime API implementation in this slice. |

## Decision Confirmed

RFC-087 implementation must not add a single
`POST /integration/portfolios/{portfolio_id}/dpm-execution-context` endpoint.

`lotus-core` will expose independently governed source-data products. `lotus-manage` will compose
those products into its own stateful DPM source context and keep execution ownership local to
`lotus-manage`.

## Existing Core Products And Routes

Existing source-data products that are useful for DPM source assembly:

| Product | Plane | Existing route coverage | DPM posture |
| --- | --- | --- | --- |
| `PortfolioStateSnapshot:v1` | `query_control_plane_service` | `POST /integration/portfolios/{portfolio_id}/core-snapshot` | Preferred governed portfolio-state source where sections are sufficient. |
| `HoldingsAsOf:v1` | `query_service` | `GET /portfolios/{portfolio_id}/positions`, `GET /portfolios/{portfolio_id}/cash-balances` | Operational read fallback/augmentation for holdings and cash. |
| `TransactionLedgerWindow:v1` | `query_service` | `GET /portfolios/{portfolio_id}/transactions` | Useful for transaction evidence; tax-lot fan-out is still a gap. |
| `InstrumentReferenceBundle:v1` | `query_control_plane_service` | `POST /integration/instruments/enrichment-bulk`, `POST /integration/reference/classification-taxonomy` | Useful for enrichment and taxonomy; DPM eligibility/restriction/settlement semantics are missing. |
| `MarketDataWindow:v1` | `query_control_plane_service` | benchmark market-series routes | Existing benchmark coverage is not enough for held and target instrument DPM valuation. |
| `DataQualityCoverageReport:v1` | `query_control_plane_service` | benchmark and risk-free coverage routes | Useful pattern; needs DPM source-family coverage. |
| `IngestionEvidenceBundle:v1` | `query_control_plane_service` | lineage, reprocessing keys, reprocessing jobs | Useful pattern for source-lineage and support evidence. |

Existing route-family metadata was verified from:

1. `src/libs/portfolio-common/portfolio_common/source_data_products.py`,
2. `docs/standards/route-contract-family-registry.json`,
3. `contracts/domain-data-products/lotus-core-products.v1.json`.

## Missing Core Products For Stateful DPM

| Missing capability | Required product/API direction |
| --- | --- |
| Model portfolio target weights, bands, approval state, and effective dating | `DpmModelPortfolioTarget:v1` |
| Portfolio-to-mandate/model/policy binding and discretionary authority status | `DiscretionaryMandateBinding:v1` |
| Product shelf, buy/sell eligibility, restriction reason codes, and settlement profile | `InstrumentEligibilityProfile:v1` |
| Portfolio-window tax lots without per-security production fan-out | `PortfolioTaxLotWindow:v1` |
| Held and target universe price/FX coverage with completeness diagnostics | `MarketDataCoverageWindow:v1` |
| DPM source-family readiness and lineage grouping | enhanced readiness/lineage support products |

These gaps are data-product and ingestion gaps, not a reason to create an all-in-one DPM context
route.

## lotus-advise Pattern Confirmed

`lotus-advise` composes core source data instead of using a monolithic source context:

1. `src/integrations/lotus_core/stateful_context.py` reads portfolio, positions, cash balances,
   enrichment, and taxonomy from `lotus-core`.
2. `src/integrations/lotus_core/simulation.py` calls the separate advisory execution route
   `POST /integration/advisory/proposals/simulate-execution`.
3. `docs/architecture/RFC-0082-upstream-contract-family-map.md` records the split between
   operational reads, analytics-input products, and advisory execution authority.

The reusable pattern for `lotus-manage` is bounded source composition with supportability and
lineage. The non-reusable part is advisory execution; DPM execution remains in `lotus-manage`.

## lotus-manage Rebaseline Findings

`lotus-manage` still had current-state docs and future-state language expecting the monolithic
`dpm-execution-context` route. Slice 0 rebaseline must update those docs to point to RFC-087
composed source products:

1. `docs/rfcs/RFC-0036-dpm-stateful-core-sourcing-and-endpoint-consolidation.md`,
2. `README.md`,
3. `docs/standards/RFC-0082-upstream-contract-family-map.md`,
4. `wiki/Integrations.md`,
5. `wiki/Overview.md`,
6. `wiki/Supported-Features.md`,
7. `wiki\Validation-and-CI.md`,
8. `wiki\Mesh-Data-Products.md`.

Runtime code still contains a feature-gated resolver client pointed at the old path. That code must
not be promoted. It should be replaced during the `lotus-manage` RFC-0036 stateful-source assembly
implementation after RFC-087 core products exist.

## Issue Disposition

Open core issue reviewed:

1. `sgajbi/lotus-core#330`
   - old title: `RFC-0036: add governed DPM execution-context source-data contract for lotus-manage`
   - updated title: `RFC-087: add composed DPM source-data products for lotus-manage`
   - disposition: issue comment `4362471271` records that RFC-087 supersedes the monolithic route
     request and that the issue now tracks composed DPM source-data products.

No open `lotus-manage` issue matching `dpm-execution-context lotus-core` was found during Slice 0
review.

## Validation Evidence

Local validation run before this slice:

1. `make route-contract-family-guard` - passed,
2. `make source-data-product-contract-guard` - passed,
3. `make domain-product-validate` - passed,
4. `git diff --check` - passed with only existing CRLF warnings.

Remote validation for the RFC-hardening baseline:

1. GitHub run: `25239500994`,
2. branch: `feat/dpm-source-data-products-rfc`,
3. commit: `df9b3b5518d1229d7e1237ef63928053a3ffb1cb`,
4. result: success,
5. passed jobs:
   - `Feature Lane / Workflow Lint`,
   - `Feature Lane / Lint Typecheck Contracts Security`,
   - `Feature Lane / Tests (unit-db)`,
   - `Feature Lane / Tests (integration-lite)`.

## Slice 0 Exit Assessment

Slice 0 is complete only after:

1. this evidence file is committed,
2. RFC-087 links this evidence file,
3. `lotus-manage` RFC-0036 and current-state docs are rebaselined to composed source products,
4. `sgajbi/lotus-core#330` is updated away from the monolithic endpoint request,
5. local and remote validation for the slice pass.
