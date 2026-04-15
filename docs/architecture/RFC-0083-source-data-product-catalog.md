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
| `HoldingsAsOf` | Operational read | `query_service` | gateway, risk, report, manage | `/portfolios/{portfolio_id}/positions`, `/reporting/holdings-snapshot/query`, `/reporting/cash-balances/query` |
| `TransactionLedgerWindow` | Operational read | `query_service` | gateway, report, manage, risk | `/portfolios/{portfolio_id}/transactions`, `/reporting/activity-summary/query`, `/reporting/income-summary/query` |
| `PositionTimeseriesInput` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/portfolios/{portfolio_id}/analytics/position-timeseries` |
| `PortfolioTimeseriesInput` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` |
| `MarketDataWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/benchmarks/{benchmark_id}/market-series` |
| `InstrumentReferenceBundle` | Analytics input | `query_control_plane_service` | performance, risk, gateway, advise | `/integration/instruments/enrichment-bulk`, `/integration/reference/classification-taxonomy` |
| `BenchmarkAssignment` | Analytics input | `query_control_plane_service` | performance, risk, report | `/integration/portfolios/{portfolio_id}/benchmark-assignment` |
| `BenchmarkConstituentWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/benchmarks/{benchmark_id}/composition-window` |
| `IndexSeriesWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/indices/{index_id}/price-series`, `/integration/indices/{index_id}/return-series` |
| `RiskFreeSeriesWindow` | Analytics input | `query_control_plane_service` | performance, risk | `/integration/reference/risk-free-series` |
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
| `/reporting/holdings-snapshot/query` | `HoldingsAsOf` |
| `/reporting/cash-balances/query` | `HoldingsAsOf` |
| `/reporting/activity-summary/query` | `TransactionLedgerWindow` |
| `/reporting/income-summary/query` | `TransactionLedgerWindow` |

Pre-live cleanup should prefer replacing these with named source-data product contracts instead of
creating aliases. If a route must remain for an existing product surface, it must declare the target
product identity and carry the same supportability metadata.

## Consumer Rules

`lotus-performance` should consume analytics-input products for portfolio and position timeseries,
benchmark/index/risk-free/reference inputs, and reconciliation/data-quality evidence when gating
analytics runs.

`lotus-risk` should consume holdings, transaction windows, market/reference windows, and evidence
products. Risk methodology, active-risk interpretation, and stress/scenario conclusions remain outside
`lotus-core`.

`lotus-gateway`, `lotus-advise`, and `lotus-manage` should consume source truth, projected state, and
evidence through gateway/product contracts without mutating core state outside command contracts.

`lotus-report` should compose reports from source-data products and evidence bundles, not direct
database assumptions or report-specific private shapes.

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
2. `PositionTimeseriesInput`.

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
3. `HoldingsSnapshotResponse`,
4. `PaginatedTransactionResponse`,
5. `IncomeSummaryResponse`,
6. `ActivitySummaryResponse`,
7. `CoreSnapshotResponse`,
8. `PortfolioAnalyticsTimeseriesResponse`,
9. `PositionAnalyticsTimeseriesResponse`,
10. `BenchmarkAssignmentResponse`,
11. `BenchmarkCompositionWindowResponse`,
12. `BenchmarkMarketSeriesResponse`,
13. `IndexPriceSeriesResponse`,
14. `IndexReturnSeriesResponse`,
15. `RiskFreeSeriesResponse`,
16. `CoverageResponse`,
17. `ClassificationTaxonomyResponse`.

The binding populates `generated_at`, `as_of_date`, `restatement_version`, and `correlation_id`
from runtime request context and deterministic defaults. It leaves
`tenant_id`, `latest_evidence_timestamp`, `source_batch_fingerprint`, `snapshot_id`, and
`policy_version` as truthful nulls until tenant enforcement, evidence linking, snapshot identity,
and policy versioning are wired for these products. `reconciliation_status` and
`data_quality_status` remain `UNKNOWN` until the reconciliation and data-quality evidence models are
joined into operational product responses.

`PortfolioStateSnapshot` additionally populates `tenant_id` and `policy_version` from the resolved
integration governance context because those values already exist in the core snapshot assembly
path. It leaves `snapshot_id` null until the reconstruction scope can supply complete epoch inputs
for deterministic snapshot identity. The core snapshot freshness block populates
`freshness.snapshot_epoch` only when the returned snapshot-backed baseline rows resolve to one
unambiguous position epoch; mixed per-security epochs remain null rather than claiming a single
portfolio-wide epoch.

The analytics-input timeseries products reuse their existing `lineage.generated_at` timestamp for
the top-level `generated_at` supportability field so lineage and envelope metadata stay internally
consistent. They leave tenant, evidence, snapshot, and policy fields null until those controls are
resolved in the analytics-input contract path.

The market/reference products populate top-level `as_of_date` from their explicit as-of request
where one exists, or from the resolved window end date for window-only products. They preserve
existing lineage dictionaries and leave evidence, snapshot, and policy fields null until reference
source-batch and quality evidence are joined into those contracts.

`DataQualityCoverageReport` additionally derives `data_quality_status` from observed coverage,
missing dates, and stale quality-status counts using `reconciliation_quality.py`. Full observed
coverage is `COMPLETE`, missing coverage is `PARTIAL`, stale observed coverage is `STALE`, and empty
observed coverage is `UNRECONCILED`.

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
   `product_name` and `product_version` defaults.

## Validation

Slice 6 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py -q`,
2. `python -m pytest tests/unit/scripts/test_source_data_product_contract_guard.py -q`,
3. `python scripts/source_data_product_contract_guard.py`,
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_products.py scripts/source_data_product_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/scripts/test_source_data_product_contract_guard.py --ignore E501,I001`,
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_products.py scripts/source_data_product_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/scripts/test_source_data_product_contract_guard.py`,
6. `git diff --check`,
7. `make lint`.
