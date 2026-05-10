# RFC-0083 Source-Data Product Catalog

This document is the RFC-0083 Slice 6 catalog for priority `lotus-core` source-data products.

It does not change runtime behavior, persistence, DTOs, OpenAPI output, or downstream contracts. It
defines the product names, owners, route mappings, required supportability metadata, paging/export
rules, and consumer map that later DTO and route slices must use.

The executable catalog is:

1. `src/libs/portfolio-common/portfolio_common/source_data_products.py`
2. `tests/unit/libs/portfolio-common/test_source_data_products.py`

## Target Principle

Downstream applications should consume named source-data products, not private database tables or
consumer-specific convenience shapes.

Each product must be versioned, owner-scoped, tenant-aware, replayable, traceable to source evidence,
and explicit about whether it is suitable for inline paging or export-oriented retrieval.

## Required Supportability Metadata

Every source-data product must expose or be able to derive these fields before it becomes a runtime
contract:

1. `product_name`,
2. `product_version`,
3. `tenant_id`,
4. `generated_at`,
5. `as_of_date`,
6. `restatement_version`,
7. `reconciliation_status`,
8. `data_quality_status`,
9. `latest_evidence_timestamp`,
10. `source_batch_fingerprint`,
11. `snapshot_id`,
12. `policy_version`,
13. `correlation_id`.

Products that do not naturally contain a field must provide a truthful null, default, or linked
evidence reference rather than omitting the concept.

## Priority Catalog

| Product | Family | Serving plane | Primary consumers | Current route mapping |
| --- | --- | --- | --- | --- |
| `PortfolioStateSnapshot` | Snapshot and simulation | `query_control_plane_service` | gateway, advise, manage, risk | `/integration/portfolios/{portfolio_id}/core-snapshot` |
| `HoldingsAsOf` | Operational read | `query_service` | gateway, risk, report, manage, advise | `/portfolios/{portfolio_id}/positions`, `/portfolios/{portfolio_id}/cash-balances` |
| `TransactionLedgerWindow` | Operational read | `query_service` | gateway, report, manage, risk | `/portfolios/{portfolio_id}/transactions` |
| `PortfolioLiquidityLadder` | Operational read | `query_service` | gateway, report, manage, advise | `/portfolios/{portfolio_id}/liquidity-ladder` |
| `PositionTimeseriesInput` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/portfolios/{portfolio_id}/analytics/position-timeseries` |
| `PortfolioTimeseriesInput` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` |
| `PortfolioAnalyticsReference` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/portfolios/{portfolio_id}/analytics/reference` |
| `MarketDataWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/benchmarks/{benchmark_id}/market-series` |
| `InstrumentReferenceBundle` | Analytics input | `query_control_plane_service` | performance, risk, gateway, advise | `/integration/instruments/enrichment-bulk`, `/integration/reference/classification-taxonomy` |
| `BenchmarkAssignment` | Analytics input | `query_control_plane_service` | performance, risk, report | `/integration/portfolios/{portfolio_id}/benchmark-assignment` |
| `BenchmarkConstituentWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/benchmarks/{benchmark_id}/composition-window` |
| `IndexSeriesWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/indices/{index_id}/price-series`, `/integration/indices/{index_id}/return-series` |
| `RiskFreeSeriesWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/reference/risk-free-series` |
| `PortfolioManagerBookMembership` | Analytics input | `query_control_plane_service` | manage | `/integration/portfolio-manager-books/{portfolio_manager_id}/memberships` |
| `TransactionCostCurve` | Analytics input | `query_control_plane_service` | manage | `/integration/portfolios/{portfolio_id}/transaction-cost-curve` |
| `ReconciliationEvidenceBundle` | Control-plane and policy | `query_control_plane_service` | performance, risk, gateway, manage | `/support/portfolios/{portfolio_id}/reconciliation-runs`, `/support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings` |
| `DataQualityCoverageReport` | Control-plane and policy | `query_control_plane_service` | performance, risk, gateway, manage | `/integration/benchmarks/{benchmark_id}/coverage`, `/integration/reference/risk-free-series/coverage` |
| `IngestionEvidenceBundle` | Control-plane and policy | `query_control_plane_service` | gateway, manage, report | `/lineage/portfolios/{portfolio_id}/keys`, `/support/portfolios/{portfolio_id}/reprocessing-keys`, `/support/portfolios/{portfolio_id}/reprocessing-jobs` |

## Paging And Export Rules

1. Small bounded products may remain inline responses.
2. Large timeseries and window products must expose deterministic paging with stable ordering.
3. Products marked export-eligible must use durable export jobs for large windows instead of forcing
   callers into long synchronous requests.
4. Export payloads must preserve the same product name, product version, request fingerprint,
   restatement version, supportability metadata, and deterministic ordering as inline responses.
5. Runtime slices must document concrete page-size limits before changing public DTOs.

## Convenience Shape Disposition

These route families are useful today but should not become the long-term product identity:

| Convenience shape | Target product |
| --- | --- |
| `/portfolios/{portfolio_id}/cash-balances` | `HoldingsAsOf` |

Pre-live cleanup should prefer replacing these with named source-data product contracts instead of
creating aliases. If a route must remain for an existing product surface, it must declare the target
product identity and carry the same supportability metadata.

## Consumer Rules

`lotus-performance` should consume analytics-input products for portfolio and position timeseries,
benchmark/index/risk-free/reference inputs, and reconciliation/data-quality evidence when gating
analytics runs.

For analytics-input cash-flow observations, `lotus-performance` should treat
`cash_flow_type="fee"` with `flow_scope="operational"` as the canonical representation of persisted
`EXPENSE` classifications. Net TWR includes the fee drag in portfolio return. Gross TWR may add back
or otherwise neutralize those fee observations according to performance methodology, but should not
expect a separate analytics-input `expense` type.

`lotus-risk` should consume holdings, transaction windows, market/reference windows, and evidence
products. Risk methodology, active-risk interpretation, and stress/scenario conclusions remain outside
`lotus-core`.

`lotus-gateway`, `lotus-advise`, and `lotus-manage` should consume source truth, projected state, and
evidence through gateway/product contracts without mutating core state outside command contracts.

`lotus-report` should compose reports from source-data products and evidence bundles, not direct
database assumptions or report-specific private shapes.

## Realized Outcome Source Boundaries

RFC42-WTBD-006 outcome reviews depend on source-owned realized evidence rather than downstream
applications reconstructing cash, tax, FX, or execution methodology from private tables. The
following `lotus-core` products are the current source boundary for those dimensions:

| Product | Source-owned evidence | Downstream rule | Explicit non-claim |
| --- | --- | --- | --- |
| `HoldingsAsOf:v1` | Portfolio positions, cash-balance totals, portfolio/base currency, as-of date, supportability metadata, latest evidence timestamp, current-epoch snapshot reconciliation, history-backed supplement posture, and cash reporting-currency restatement. The implementation-backed methodology is documented in `docs/methodologies/source-data-products/holdings-as-of.md`. | Consumers may use returned cash totals and holdings rows as source facts with the product metadata attached. | Consumers must not infer liquidity ladders, income need, performance returns, risk exposure methodology, tax advice, execution quality, or OMS acknowledgement from holdings or cash totals alone. |
| `MarketDataCoverageWindow:v1` | Held and target universe price and FX coverage diagnostics, observation dates, staleness age, requested/resolved counts, missing and stale identifiers, valuation-currency context, supportability state, and latest evidence timestamp. The implementation-backed methodology is documented in `docs/methodologies/source-data-products/market-data-coverage-window.md`. | Consumers may use coverage rows and supportability to route valuation, drift, cash-conversion, and rebalance-sizing readiness. | Consumers must not infer portfolio valuation, FX attribution, liquidity ladders, cash forecasts, market impact, best execution, venue routing, or OMS acknowledgement from coverage diagnostics alone. |
| `DpmSourceReadiness:v1` | Fail-closed source-family readiness over mandate binding, model targets, eligibility, tax lots, and market-data coverage, including family state counts, missing/stale items, evidence counts, resolved mandate/model identifiers, and runtime source-data metadata. The implementation-backed methodology is documented in `docs/methodologies/source-data-products/dpm-source-readiness.md`. | Consumers may gate DPM workflow promotion and route operators to the source family that is unavailable, incomplete, or degraded while preserving source-owned reason codes. | Consumers must not infer mandate approval, suitability, valuation, FX attribution, liquidity ladders, execution quality, best execution, venue routing, or OMS acknowledgement from readiness alone. |
| `TransactionLedgerWindow:v1` | Deterministically ordered booked transaction rows, trade fees, transaction-cost records, withholding tax, other interest deductions, net interest, realized capital/FX/total P&L fields, linked cashflow records, FX/event linkage identifiers, and optional reporting-currency restatements, including explicit row-level realized FX P&L local evidence. The implementation-backed methodology is documented in `docs/methodologies/source-data-products/transaction-ledger-window.md`. | Consumers may preserve explicit row-level measures, lineage, supportability posture, source field, source unit, selected row identity, and optional `realized_fx_pnl_local_reporting_currency` for reporting surfaces. | Consumers must not aggregate rows into tax methodology, FX attribution, cash movement methodology, transaction-cost methodology, or execution-quality conclusions unless a source owner publishes that methodology. |
| `PortfolioCashflowProjection:v1` | Daily booked cashflow, projected settlement cashflow, net cashflow points, cumulative cashflow across the returned window, booked/projected/net totals, portfolio currency, include-projected posture, evidence timestamp, and deterministic source fingerprint. | Consumers may use the returned component totals and points as core-owned operational cashflow evidence. | Consumers must not treat the projection as a liquidity ladder, funding recommendation, income plan, OMS execution forecast, market-impact estimate, or client cash-need methodology. |
| `PortfolioLiquidityLadder:v1` | Source cash balance, deterministic cash-availability buckets, booked and projected settlement cashflow contributions by bucket, cumulative cash available, maximum cash shortfall, non-cash asset exposure by source-owned instrument liquidity tier, supportability metadata, evidence timestamp, and deterministic source fingerprint. The implementation-backed methodology is documented in `docs/methodologies/source-data-products/portfolio-liquidity-ladder.md`. | Consumers may use the returned bucket and tier evidence as source-owned liquidity facts for monitoring, reporting, DPM supportability, and client-facing explanation with source refs attached. | Consumers must not treat the ladder as advice, funding recommendation, income plan, OMS execution forecast, best-execution assessment, tax methodology, or predictive market-impact model. |
| `PortfolioTaxLotWindow:v1` | Effective tax-lot and cost-basis state for tax-aware discretionary sell decisions. The implementation-backed methodology is documented in `docs/methodologies/source-data-products/portfolio-tax-lot-window.md`. | Consumers may use lot quantity, acquisition date, cost basis, source transaction lineage, calculation policy metadata, and source supportability to explain candidate sell allocation. | Consumers must not claim complete jurisdiction-specific tax advice, realized-tax optimization, wash-sale treatment, client-tax approval, or tax-reporting certification from lot state alone. |
| `TransactionCostCurve:v1` | Observed booked fee evidence grouped by security, transaction type, and currency. | Consumers may distinguish source-backed observed cost context from local estimated construction cost. | Consumers must not claim predictive market-impact, venue-routing, fill-quality, best-execution, or minimum-cost execution methodology from observed fee evidence. |

These boundaries are intentionally conservative. `lotus-core` is the source authority for recorded
portfolio, transaction, cashflow, tax-lot, and observed-fee facts; it is not the owner of
performance returns, risk methodology, client tax advice, liquidity planning, execution routing, or
post-trade OMS acknowledgement methodology. Downstream products must carry source refs and
supportability metadata and must degrade when a required source product is unavailable, partial,
stale, or outside its explicit methodology boundary.

`HoldingsAsOf:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/holdings-as-of.md`. The method resolves booked and
projected-inclusive holdings modes, reconciles snapshot-backed positions to the latest
current-epoch history quantity, supplements missing snapshot securities from position history,
preserves valuation continuity for history-backed rows, computes weights from returned position
values, derives `held_since_date` within the active epoch, classifies unknown, partial, stale, and
complete data-quality posture, and restates cash balances into a requested reporting currency
without claiming liquidity planning, performance, risk, tax, or execution methodology.

`MarketDataCoverageWindow:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/market-data-coverage-window.md`. The method resolves
latest market prices and FX rates on or before the requested as-of date, preserves per-instrument
and per-pair request order, classifies missing and stale observations, derives batch
supportability, and preserves the non-claim boundary from valuation methodology, FX attribution,
liquidity ladders, cash forecasts, market impact, best execution, venue routing, and OMS
acknowledgement.

`DpmSourceReadiness:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/dpm-source-readiness.md`. The method composes
`DiscretionaryMandateBinding:v1`, `DpmModelPortfolioTarget:v1`,
`InstrumentEligibilityProfile:v1`, `PortfolioTaxLotWindow:v1`, and
`MarketDataCoverageWindow:v1`; unions request and model-target instruments; counts family states;
and applies fail-closed precedence where `UNAVAILABLE` outranks `INCOMPLETE`, which outranks
`DEGRADED`, which outranks `READY`. It preserves the non-claim boundary from mandate approval,
suitability, valuation, FX attribution, liquidity, execution quality, best execution, venue
routing, and OMS acknowledgement.

`TransactionLedgerWindow:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/transaction-ledger-window.md`. The method filters booked
rows by portfolio, optional instrument/security, transaction type, FX/event linkage, date window,
and effective as-of date; preserves joined row-level transaction-cost and cashflow evidence;
populates optional reporting-currency fields from latest available FX rates, including
`realized_fx_pnl_local_reporting_currency`; classifies empty, complete, and paged windows; and
preserves the non-claim boundary from tax advice, FX attribution, cash-movement aggregation,
transaction-cost methodology, execution quality, and OMS acknowledgement.

`PortfolioLiquidityLadder:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/portfolio-liquidity-ladder.md`. The method resolves
source cash balances from current holdings, groups non-cash exposure by instrument liquidity tier,
loads booked and optional projected settlement cashflows, builds deterministic T0, T+1, T+2-to-T+7,
T+8-to-T+30, and T+31-to-horizon buckets, calculates cumulative cash availability and cash
shortfall, and preserves the non-claim boundary from advice, funding recommendation, income
planning, OMS execution, best execution, tax, and market-impact forecasting.

`TransactionCostCurve:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/transaction-cost-curve.md`. The method groups observed
booked-fee evidence by security, transaction type, and currency; uses explicit transaction-cost
rows ahead of `trade_fee`; excludes zero-fee and zero-notional observations; computes
notional-weighted average cost bps plus min/max per-transaction cost bps; and preserves the
non-claim boundary from predictive market-impact, venue-routing, best-execution, OMS
acknowledgement, and minimum-cost execution methodology.

`PortfolioTaxLotWindow:v1` now has implementation-backed methodology truth in
`docs/methodologies/source-data-products/portfolio-tax-lot-window.md`. The method selects
effective-dated lots from `position_lot_state`, applies open/closed lot filtering, preserves
base/local cost-basis fields, carries source transaction and calculation-policy lineage, uses
deterministic paging, reports empty full-portfolio source evidence explicitly, and preserves the
non-claim boundary from jurisdiction-specific tax advice, realized-tax optimization, wash-sale
treatment, client-tax approval, and tax-reporting certification.

## Portfolio Performance Snapshot Boundary

The portfolio workspace performance snapshot is not a `lotus-core` source-data product.

`lotus-core` owns the source inputs required by that feature:

1. `PortfolioAnalyticsReference` for portfolio currency, lifecycle, and performance horizon bounds,
2. `PortfolioTimeseriesInput` for valuation and cash-flow economics,
3. `BenchmarkAssignment` for effective benchmark mapping,
4. `BenchmarkConstituentWindow`, `IndexSeriesWindow`, and `RiskFreeSeriesWindow` for benchmark,
   excess-return, and risk-free source inputs,
5. `DataQualityCoverageReport` and `ReconciliationEvidenceBundle` for readiness evidence.

`lotus-performance` owns the calculated portfolio return, benchmark return, excess return, and
compact return path used by the book workspace. `lotus-gateway` and UI surfaces should consume the
performance-owned snapshot contract and may use `lotus-core` readiness evidence only to explain
source availability. They must not recompute performance returns from raw `lotus-core` inputs.

## Runtime Follow-Up

Future runtime slices must:

1. add `product_name` and `product_version` to affected DTO envelopes,
2. wire snapshot ids from `reconstruction_identity.py`,
3. wire source batch fingerprints from `ingestion_evidence.py`,
4. wire reconciliation and data-quality statuses from `reconciliation_quality.py`,
5. preserve RFC-0082 route-family classification,
6. update downstream contract tests for affected consumers.

## Runtime Binding Progress

The first runtime-adjacent binding exposes machine-readable source-data product identity in OpenAPI
through `x-lotus-source-data-product` for all catalog-backed `query_control_plane_service` routes and
the catalog-backed `query_service` operational read routes.

The extension is generated from the executable catalog and includes product name, version, route
family, serving plane, owner, consumers, current route set, paging mode, export mode, and required
metadata fields. Contract tests verify that every `query_control_plane_service` and `query_service`
route listed in the catalog carries matching OpenAPI metadata.

This binding does not change response payloads, persistence, generated events, or downstream runtime
behavior. It makes the catalog visible to contract consumers and keeps the full DTO-envelope metadata
work as a later runtime slice.

The first DTO-envelope binding adds `product_name` and `product_version` to:

1. `PortfolioTimeseriesInput`,
2. `PositionTimeseriesInput`,
3. `PortfolioAnalyticsReference`.

The next DTO-envelope binding adds the same additive fields to the reference and quality products
that already have catalog-backed control-plane routes:

1. `BenchmarkAssignment`,
2. `BenchmarkConstituentWindow`,
3. `MarketDataWindow`,
4. `IndexSeriesWindow`,
5. `RiskFreeSeriesWindow`,
6. `DataQualityCoverageReport`,
7. `InstrumentReferenceBundle`.

These fields are additive defaults on the response envelopes. They do not alter request semantics,
persistence, eventing, paging, or calculation behavior.

The operational read DTO-envelope binding adds `product_name` and `product_version` to:

1. `HoldingsAsOf`,
2. `TransactionLedgerWindow`.

These fields cover the canonical positions and transaction ledger responses plus the pre-live
reporting convenience shapes that are already deprecated toward those target products.

The first runtime metadata binding adds the required supportability fields to the
`HoldingsAsOf`, `TransactionLedgerWindow`, `PortfolioStateSnapshot`, analytics-input, and
market/reference response envelopes:

1. `PortfolioPositionsResponse`,
2. `CashBalancesResponse`,
3. `PaginatedTransactionResponse`,
4. `CoreSnapshotResponse`,
5. `PortfolioAnalyticsTimeseriesResponse`,
6. `PositionAnalyticsTimeseriesResponse`,
7. `PortfolioAnalyticsReferenceResponse`,
8. `BenchmarkAssignmentResponse`,
9. `BenchmarkCompositionWindowResponse`,
10. `BenchmarkMarketSeriesResponse`,
11. `IndexPriceSeriesResponse`,
12. `IndexReturnSeriesResponse`,
13. `RiskFreeSeriesResponse`,
16. `CoverageResponse`,
17. `ClassificationTaxonomyResponse`.

The initial binding populated `generated_at`, `as_of_date`, `restatement_version`, and
`correlation_id` from runtime request context and deterministic defaults. It left `tenant_id`,
`latest_evidence_timestamp`, `source_batch_fingerprint`, `snapshot_id`, `policy_version`,
`reconciliation_status`, and `data_quality_status` as truthful null or `UNKNOWN` defaults until
later runtime slices could wire product-specific evidence without overclaiming lineage. The sections
below record the fields that are now derived from durable runtime evidence and the fields that
remain unresolved.

`HoldingsAsOf` portfolio-position responses additionally derive `data_quality_status` from returned
position evidence. Fully snapshot-backed current holdings are `COMPLETE`; current holdings that
depend on history-backed fallback or supplement rows are `PARTIAL`; holdings with any non-current
position-state status are `STALE`; empty holdings or holdings without position-state evidence remain
`UNKNOWN`. The response also populates `latest_evidence_timestamp` from durable position-row and
position-state timestamps when available. Deprecated reporting convenience responses that still map
to `HoldingsAsOf`, such as cash balances and holdings snapshots, populate
`latest_evidence_timestamp` from the returned daily-position snapshot rows while they remain
available during pre-live endpoint consolidation.

The canonical `TransactionLedgerWindow` portfolio transaction response populates
`latest_evidence_timestamp` from the latest durable transaction-row update timestamp across the
filtered ledger window, independent of the requested page. It derives `data_quality_status` from the
completeness of the returned ledger window: complete unpaginated windows are `COMPLETE`, paginated
or offset windows are `PARTIAL`, and empty windows remain `UNKNOWN`. It continues to leave
reconciliation, source-batch, and snapshot fields at truthful unresolved defaults until
transaction-level reconciliation and source-lineage evidence are joined into the ledger response
path. Deprecated reporting convenience responses that still map to `TransactionLedgerWindow`, such
as income and activity summaries, populate the same evidence timestamp from the transaction rows
included in their year-to-date aggregation windows while leaving data-quality status unresolved.

`PortfolioStateSnapshot` additionally populates `tenant_id` and `policy_version` from the resolved
integration governance context because those values already exist in the core snapshot assembly
path. Snapshot-backed baseline responses populate `freshness.snapshot_timestamp` and top-level
`latest_evidence_timestamp` from durable position snapshot and position-state timestamps. Historical
fallback baselines leave those fields null because they are not resolved snapshot evidence. The
response derives `data_quality_status` from baseline evidence: current snapshot-backed baselines with
durable timestamp and one unambiguous position epoch are `COMPLETE`, historical fallback baselines
are `PARTIAL`, snapshot-backed baselines missing complete epoch or timestamp evidence are `PARTIAL`,
and empty baselines remain `UNKNOWN`. The response leaves `snapshot_id` null until the
reconstruction scope can supply complete epoch inputs for deterministic snapshot identity. The core
snapshot freshness block populates `freshness.snapshot_epoch` only when the returned
snapshot-backed baseline rows resolve to one unambiguous position epoch; mixed per-security epochs
remain null rather than claiming a single portfolio-wide epoch.

The analytics-input timeseries products reuse their existing `lineage.generated_at` timestamp for
the top-level `generated_at` supportability field so lineage and envelope metadata stay internally
consistent. They derive `data_quality_status` from expected/observed valuation dates, stale or
restated points, and pagination completeness using the shared reconciliation-quality helper: fully
observed final windows are `COMPLETE`, paginated responses are `PARTIAL`, stale or restated returned
points are `STALE`, missing expected dates are `PARTIAL`, and empty windows remain `UNKNOWN` or
`UNRECONCILED` depending on whether the request had expected dates. They leave tenant, evidence,
snapshot, and policy fields null until those controls are resolved in the analytics-input contract
path.

The analytics-input serving path also normalizes day-boundary beginning capital for TWR safety.
Persisted position-timeseries BOD values that are stale relative to prior EOD state are repaired at
the contract boundary when the position was active on the immediately preceding observation date.
Positions that reappear after an absent date are not carried forward from stale historical rows;
if they are backed by internal position-flow evidence and no portfolio-level external flow, they are
treated as new internal beginning capital instead of artificial returns from zero. This preserves
downstream economics without changing source persistence or inventing portfolio-level external cash
flows.

`PortfolioAnalyticsReference` is the analytics-safe portfolio reference context consumed by
`lotus-performance` and `lotus-risk`. It is catalog-backed on the query control plane and publishes
the same product identity and runtime metadata envelope as the analytics-input timeseries products.
It reuses the existing lineage timestamp for top-level `generated_at`, marks the reference
`COMPLETE` when the portfolio can be bounded by a portfolio performance horizon, marks it `PARTIAL`
when the portfolio exists but no performance horizon is available, and derives
`latest_evidence_timestamp` from durable portfolio source/update/create timestamps when those fields
are available.

The market/reference products populate top-level `as_of_date` from their explicit as-of request
where one exists, or from the resolved window end date for window-only products. They preserve
existing lineage dictionaries, derive `data_quality_status` from returned row quality statuses using
`market_reference_quality.py`, and populate `latest_evidence_timestamp` from durable returned-row
source/update evidence where available. They continue to leave source-batch fingerprints,
deterministic snapshot ids, and policy fields null until reference source-batch lineage and
snapshot identity are joined into those contracts.

`DataQualityCoverageReport` additionally derives `data_quality_status` from observed coverage,
missing dates, and stale quality-status counts using `reconciliation_quality.py`. Full observed
coverage is `COMPLETE`, missing coverage is `PARTIAL`, stale observed coverage is `STALE`, and empty
observed coverage is `UNRECONCILED`. Coverage reports populate `latest_evidence_timestamp` when the
repository can resolve durable evidence timestamps from the underlying benchmark, index, or
risk-free rows used to calculate coverage.

The snapshot DTO-envelope binding adds `product_name` and `product_version` to
`PortfolioStateSnapshot` on the core snapshot response. The existing route-level
`x-lotus-source-data-product` metadata remains the route discovery mechanism; the response fields
make the resolved product identity visible in generated client models and runtime payloads.

The evidence DTO-envelope binding adds `product_name` and `product_version` to
`IngestionEvidenceBundle` lineage-key, reprocessing-key, and reprocessing-job responses, and to
`ReconciliationEvidenceBundle` run and finding responses. The reprocessing-job binding uses a
dedicated `ReprocessingJobListResponse` envelope so generic valuation and aggregation support-job
responses do not claim ingestion evidence semantics.

The evidence products also expose runtime supportability metadata. They set top-level
`generated_at` equal to the existing support snapshot `generated_at_utc`, derive `as_of_date` from
durable evidence business dates or watermarks when rows are present, and populate
`latest_evidence_timestamp` from durable update/completion/creation timestamps when available.
Empty evidence listings fall back to the response generation date for `as_of_date` and leave
`latest_evidence_timestamp` null. Tenant, source batch, deterministic snapshot, and policy fields
remain null until those controls are joined to the evidence response path.
`ReconciliationEvidenceBundle` additionally derives `reconciliation_status` from returned run
statuses and finding severities using `reconciliation_quality.py`, with blocking evidence taking
precedence over partial or complete evidence.

The source-data product contract guard statically checks both sides of the binding:

1. every catalog route must carry matching `x-lotus-source-data-product` route metadata,
2. every catalog route must declare a response model whose DTO envelope exposes matching
   `product_name` and `product_version` defaults,
3. every catalog-backed route helper must expose `x-lotus-source-data-security` metadata that
   matches the governed RFC-0083 Slice 9 security profile.

The analytics-input consumer contract guard adds explicit downstream-consumer conformance checks for
`lotus-performance` and `lotus-risk`. It verifies that the declared performance-facing products are
exactly the governed analytics/supportability products, that those products are served from the query
control plane rather than operational reads, and that the analytics cash-flow vocabulary remains
`external_flow`, `internal_trade_flow`, `income`, `fee`, `transfer`, and `other`. It also verifies
that the declared risk-facing products cover operational holdings, transaction windows, snapshot
state, analytics-input market/reference products, and evidence products on the governed serving plane
for each route family.

## Validation

Slice 6 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py -q`,
2. `python -m pytest tests/unit/scripts/test_source_data_product_contract_guard.py -q`,
3. `python -m pytest tests/unit/scripts/test_analytics_input_consumer_contract_guard.py -q`,
4. `python scripts/source_data_product_contract_guard.py`,
5. `python scripts/analytics_input_consumer_contract_guard.py`,
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_products.py scripts/source_data_product_contract_guard.py scripts/analytics_input_consumer_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/scripts/test_source_data_product_contract_guard.py tests/unit/scripts/test_analytics_input_consumer_contract_guard.py --ignore E501,I001`,
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_products.py scripts/source_data_product_contract_guard.py scripts/analytics_input_consumer_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/scripts/test_source_data_product_contract_guard.py tests/unit/scripts/test_analytics_input_consumer_contract_guard.py`,
8. `git diff --check`,
9. `make lint`.
