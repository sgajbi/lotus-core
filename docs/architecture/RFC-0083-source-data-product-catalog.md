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
through `x-lotus-source-data-product` for all catalog-backed `query_control_plane_service` routes.

The extension is generated from the executable catalog and includes product name, version, route
family, serving plane, owner, consumers, current route set, paging mode, export mode, and required
metadata fields. Contract tests verify that every `query_control_plane_service` route listed in the
catalog carries matching OpenAPI metadata.

This binding does not change response payloads, persistence, generated events, or downstream runtime
behavior. It makes the catalog visible to contract consumers and keeps the full DTO-envelope metadata
work as a later runtime slice.

## Validation

Slice 6 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_products.py tests/unit/libs/portfolio-common/test_source_data_products.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_products.py tests/unit/libs/portfolio-common/test_source_data_products.py`,
4. `git diff --check`,
5. `make lint`.
