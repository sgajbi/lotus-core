# RFC-0083 Target-State Gap Analysis

- Status: Draft
- Date: 2026-04-15
- Scope: `lotus-core`
- Source RFC: `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0083-lotus-core-system-of-record-target-architecture.md`
- Boundary RFC: `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0082-lotus-core-domain-authority-and-analytics-serving-boundary-hardening.md`
- Related local inventory: `docs/architecture/RFC-0082-contract-family-inventory.md`

## Purpose

This document is the RFC-0083 Slice 0 gap analysis for `lotus-core`.

It maps the current repository reality to the target architecture in RFC-0083 and identifies the
implementation slices needed to make `lotus-core` the banking-grade system of record before first
production release.

This slice does not change runtime behavior, database schema, OpenAPI output, or downstream
contracts. It establishes the implementation map.

## Executive Summary

`lotus-core` already contains many of the capabilities required by RFC-0083:

1. an operational read plane in `query_service`,
2. a downstream contract/control plane in `query_control_plane_service`,
3. ingestion, replay, DLQ, and job bookkeeping surfaces,
4. financial reconciliation surfaces,
5. transaction, position, cashflow, timeseries, market-data, benchmark, index, and reference tables,
6. correlation, idempotency, source-system, and job lineage fields in important paths.

The main gap is not that the repository lacks all required machinery. The gap is that the machinery is
not yet expressed as one coherent system-of-record contract.

The highest-priority target-state gaps are:

1. temporal vocabulary is inconsistent and does not yet enforce the RFC-0083 model across contracts,
2. source-data products exist as route clusters and DTOs, but not as uniformly named, versioned,
   provenance-bearing product contracts,
3. portfolio reconstruction and restatement semantics are not yet explicit enough for audit-grade
   historical explanation,
4. ingestion, replay, reconciliation, and data-quality evidence are present but not packaged as
   consumer-usable evidence bundles,
5. several endpoint families are useful today but can drift into convenience contracts unless they are
   consolidated behind stable source-data products,
6. tenancy, entitlement, retention, and supportability metadata appear in some integration contracts but
   are not yet a universal contract property for core source truth.

## Current Route-To-Target-Domain Map

| RFC-0083 target domain | Current modules and routes | Current state | Gap |
| --- | --- | --- | --- |
| Portfolio Registry | `query_service` portfolio routes, `ingestion_service` portfolio routes, `portfolios` table | Strong baseline for identity and reads | Lifecycle, custody, mandate, and temporal lifecycle semantics need a governed target contract |
| Account and Custody | `cash_accounts` query routes, cash account master data | Partial coverage | Custody/account relationship is not yet a first-class bounded domain with complete lifecycle and evidence rules |
| Transaction Booking | `ingestion_service` transaction routes, `query_service` transaction routes, `transactions`, `transaction_costs` | Strong operational baseline | Booking commands, corrections, cancellations, restatement versioning, and audit evidence need explicit command contracts |
| Position State | `positions`, `position-history`, buy/sell state routes, position history and lot-state tables | Strong calculation and read baseline | Reconstruction contract and deterministic as-of explanation are not yet first-class source-data products |
| Cash Ledger | cash accounts, cashflows, settlement-linked buy/sell cash linkage | Partial baseline | Cash ledger truth needs clearer relationship to transaction booking, settlement, and reconciliation status |
| Instrument Master | `instruments`, enrichment, taxonomy, lookthrough, reference routes | Strong reference baseline | Instrument/reference bundle needs a stable source-data product contract and boundary from advisory suitability |
| Market Data | `prices`, `fx-rates`, market price and FX ingestion | Strong baseline | Raw operational market-data reads and analytics-safe market-data windows need explicit product semantics |
| Benchmark and Reference Series | benchmark assignment, composition, index series, risk-free series integration routes and tables | Strong baseline | Product names, versioning, freshness, completeness, and lineage need to be standardized |
| Ingestion and Validation | ingestion upload/bundle routes, job bookkeeping, reprocessing | Strong operational baseline | Validation report and ingestion evidence bundle need stable product contracts |
| Reconciliation and Data Quality | `financial_reconciliation_service`, ingestion health, coverage/readiness/support routes | Partial to strong baseline | Evidence needs to be consumable by downstream services without database or log inspection |
| Source-Data Products | analytics input routes, snapshot routes, export lifecycle | Partial baseline | Product catalog, DTO minimum fields, and version/deprecation policy need implementation |
| Control Plane and Supportability | capabilities, policy, support, lineage, replay, DLQ | Strong baseline | These routes need consistent supportability metadata and endpoint ownership tests |

## Current Model-To-Target-Domain Map

| Target area | Current tables or models | Assessment |
| --- | --- | --- |
| Portfolio identity and lifecycle | `portfolios`, `business_dates` | Present; lifecycle semantics need sharper domain naming and temporal rules |
| Simulation state | `simulation_sessions`, `simulation_changes` | Present; must remain snapshot/simulation, not advisory decisioning |
| Position state | `position_history`, `daily_position_snapshots`, `position_lot_state`, `accrued_income_offset_state`, `position_state` | Strong baseline; reconstruction and restatement semantics need hardening |
| Market and FX | `market_prices`, `fx_rates` | Present; observed/source timestamp semantics need alignment with RFC-0083 |
| Instrument and reference | `instruments`, `classification_taxonomy`, `instrument_lookthrough_components`, `cash_account_masters` | Present; needs source-product packaging and supportability metadata |
| Benchmark and series | `portfolio_benchmark_assignments`, `benchmark_definitions`, `index_definitions`, `benchmark_composition_series`, `index_price_series`, `index_return_series`, `benchmark_return_series`, `risk_free_series` | Present; needs stable source-data product rules |
| Transactions and cashflows | `transactions`, `transaction_costs`, `cashflows` | Strong baseline; booking/correction/restatement command model is the main gap |
| Time series | `position_timeseries`, `portfolio_timeseries` | Present; analytics-input products need uniform provenance and completeness semantics |
| Idempotency and events | `processed_events`, `outbox_events` | Present; source-data products should reference event and batch lineage consistently |
| Jobs and ingestion operations | `portfolio_aggregation_jobs`, `portfolio_valuation_jobs`, `ingestion_jobs`, `ingestion_job_failures`, `ingestion_ops_control`, `reprocessing_jobs`, `analytics_export_jobs`, `pipeline_stage_state` | Strong operational baseline; evidence bundle contract remains the gap |
| Replay and DLQ | `consumer_dlq_events`, `consumer_dlq_replay_audit` | Present; downstream-safe evidence shape should be standardized |
| Reconciliation | `financial_reconciliation_runs`, `financial_reconciliation_findings` | Present; needs link to portfolio/data-quality source products |
| Cashflow rules | `cashflow_rules` | Present; keep as core source logic and avoid downstream report composition drift |

## Temporal Gap Analysis

RFC-0083 requires time to be an explicit domain model. Current `lotus-core` already uses several good
domain-specific names, but it also has generic or ambiguous names that should not spread into new
contracts.

| RFC-0083 concept | Current evidence | Gap |
| --- | --- | --- |
| `trade_date` | Present on instruments and transaction-adjacent models | Keep and standardize where trade execution truth is exposed |
| `settlement_date` | Present on transaction models and cash/settlement flows | Make settlement behavior explicit in cash ledger and reconciliation products |
| `booking_date` | Not found as a clear first-class concept in the current inventory | Add as a target command/read concept before booking hardening |
| `effective_date` | Present in simulation changes and some policy-style flows | Define when it means correction effectivity versus simulation effectivity |
| `valuation_date` | Present in valuation jobs and read DTOs | Standardize for valuation inputs and portfolio state snapshots |
| `as_of_date` | Common in DTOs and read paths | Keep as read-model request semantics, not a generic substitute for all dates |
| `ingested_at` | Present in several ingestion and job paths | Make mandatory on source-data products that represent externally sourced data |
| `observed_at` | Current code more often uses `source_timestamp` | Standardize `observed_at` and map or migrate from `source_timestamp` where appropriate |
| `corrected_at` | Not consistently visible as a first-class field | Required for correction and restatement slices |
| `restatement_version` | Not visible in the current inventory | Required for deterministic historical replay and source-data product versioning |

Generic names such as `date`, `series_date`, `aggregation_date`, `source_timestamp`, and route-local
date parameters should be reviewed before they become public contract precedent.

## Source-Data Product Equivalence Map

| RFC-0083 product | Current equivalent | Status | First implementation action |
| --- | --- | --- | --- |
| `PortfolioStateSnapshot` | `/integration/portfolios/{portfolio_id}/core-snapshot`, simulation source sections | Partial | Define required provenance, policy, completeness, and restatement fields |
| `HoldingsAsOf` | positions, position history, cash accounts, reporting holdings/cash queries | Partial | Consolidate as a named holdings source-data product |
| `TransactionLedgerWindow` | portfolio transactions and reporting activity queries | Partial | Add booking/correction/restatement and deterministic paging semantics |
| `PositionTimeseriesInput` | `/integration/portfolios/{portfolio_id}/analytics/position-timeseries`, `position_timeseries` | Strong baseline | Normalize product metadata and freshness/completeness signals |
| `PortfolioTimeseriesInput` | `/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`, `portfolio_timeseries` | Strong baseline | Normalize product metadata and export semantics |
| `MarketDataWindow` | prices, FX, market/reference integration routes | Partial | Separate operational raw reads from analytics-safe windows |
| `InstrumentReferenceBundle` | instruments, enrichment bulk, taxonomy, lookthrough | Partial | Package reference primitives as a stable bundle contract |
| `BenchmarkAssignment` | benchmark assignment route and table | Strong baseline | Add product-level provenance and version/deprecation rules |
| `BenchmarkConstituentWindow` | benchmark composition window route and table | Strong baseline | Add completeness and observed/ingested timestamp semantics |
| `IndexSeriesWindow` | index price and return series routes and tables | Strong baseline | Standardize freshness, paging, and source lineage |
| `RiskFreeSeriesWindow` | risk-free series route and table | Strong baseline | Standardize source lineage and coverage metadata |
| `ReconciliationEvidenceBundle` | financial reconciliation routes and findings | Partial | Create a consumer-safe evidence product linked to portfolios and source scope |
| `DataQualityCoverageReport` | coverage, readiness, support, and SLO routes | Partial | Define one governed report shape for downstream gating |
| `IngestionEvidenceBundle` | ingestion jobs, failures, replay, DLQ, audit routes | Partial | Define evidence bundle shape across ingestion and replay services |

## Endpoint Consolidation Watchlist

These endpoint families are useful, but they must be controlled so `lotus-core` does not grow
consumer-specific convenience APIs instead of durable source-data products.

| Surface | Risk | Target disposition |
| --- | --- | --- |
| `/reporting/*/query` | Can drift into report composition | Keep as source-data query surfaces or migrate into named source-data products |
| `/portfolios/{id}/cashflow-projection` | Can drift into forecasting or performance logic | Keep as core-derived cashflow source data; performance interpretation stays outside core |
| `/simulation-sessions/{id}/projected-summary` | Can drift into advisory or manage recommendations | Keep as deterministic projected state only |
| benchmark and index catalog/series routes | Can duplicate raw price/reference routes | Align behind benchmark/reference source-data products |
| `/integration/instruments/enrichment-bulk` | Can blur source reference and advisory enrichment | Keep as instrument reference source data only |
| `/integration/advisory/proposals/simulate-execution` | Can become advisory decisioning | Keep as snapshot/simulation of core source effects, not recommendation logic |
| operational prices/FX versus analytics market-data inputs | Consumers may choose inconsistent source shapes | Provide clear operational-read versus analytics-input product rules |

## Consumer Impact Matrix

| Consumer | Current dependency posture | RFC-0083 target impact |
| --- | --- | --- |
| `lotus-performance` | Consumes analytics inputs, time series, benchmark/reference primitives | Should move to named source-data products with provenance, completeness, freshness, and restatement semantics |
| `lotus-risk` | Consumes holdings, prices, FX, benchmark/reference primitives | Should consume stable holdings/market/reference windows rather than route-specific convenience shapes |
| `lotus-gateway` | Should aggregate domain services for UI experience | Should expose gateway product contracts while preserving core source provenance and not bypassing source-data products |
| `lotus-advise` | Needs projected state and advisory simulation inputs | Should consume snapshots/projections only; suitability and recommendation logic remain in advise |
| `lotus-manage` | Needs portfolio state, operational readiness, and workflow source facts | Should consume source truth and workflow-relevant evidence, not mutate core state outside command contracts |
| `lotus-report` | Needs auditable source data and evidence | Should compose reports from source-data products and evidence bundles, not from private database assumptions |

## Security, Tenancy, Lifecycle, And Observability Gaps

Current integration DTOs and control-plane surfaces already expose useful metadata such as tenant,
policy, capability, supportability, correlation, trace, and idempotency fields in important paths.

RFC-0083 requires these to become uniform contract properties:

1. every source-data product should be tenant-scoped,
2. every externally meaningful mutation should be actor, source-system, correlation, and idempotency
   aware,
3. every downstream-facing product should expose policy/supportability context where access or
   readiness can affect interpretation,
4. retention and archival posture should be explicit for source records, evidence bundles, snapshots,
   and exports,
5. product-level SLOs should cover freshness, completeness, latency, replayability, and diagnosability.

## Implementation Slice Recommendation

| Slice | Goal | Primary output |
| --- | --- | --- |
| 0 | Current-state gap analysis | This document and repo context links |
| 1 | Temporal vocabulary and schema policy | Temporal field policy, contract vocabulary updates, schema guard plan |
| 2 | Command/read route classification enforcement | Route family tests and OpenAPI metadata checks aligned to RFC-0082 |
| 3 | Source-data product catalog | Named product catalog, minimum metadata, DTO template, owner/version matrix |
| 4 | Portfolio reconstruction and snapshot lineage | Deterministic snapshot and reconstruction semantics |
| 5 | Ingestion and source-lineage hardening | Source batch, validation, replay, and lineage evidence rules |
| 6 | Reconciliation and data-quality evidence | Consumer-safe reconciliation and coverage products |
| 7 | Market/reference/benchmark product hardening | Market, FX, instrument, benchmark, index, and risk-free product contracts |
| 8 | Endpoint consolidation | Watchlist cleanup, migrations, aliases/deprecations, consumer migration notes |
| 9 | Security, tenancy, retention, and entitlement | Uniform access, policy, audit, and lifecycle controls |
| 10 | Observability and eventing | Product SLOs, supportability APIs, change notification contract |
| 11 | Production closure | Final contract tests, docs, migration notes, and platform validation evidence |

## Validation Lane By Slice

| Slice type | Minimum local validation | PR merge validation trigger |
| --- | --- | --- |
| Documentation-only architecture slice | `git diff --check`; link/path review | No runtime gate unless docs alter commands or standards |
| OpenAPI or route metadata | repo-native OpenAPI/vocabulary/no-alias checks plus targeted tests | `make ci` or GitHub-backed PR merge gate |
| DTO or contract shape | targeted unit/contract tests and generated OpenAPI diff | consumer contract validation for affected downstream repos |
| Database schema or migration | migration smoke, targeted DB tests, schema review | full PR merge gate plus migration validation |
| Ingestion/replay/reconciliation behavior | targeted unit, integration-lite, and ops-contract tests | full PR merge gate and failure-recovery evidence |
| Consumer migration | affected repo tests and gateway checks when UI-facing | cross-repo validation and platform evidence as needed |

## Slice 0 Acceptance

Slice 0 is complete when:

1. the current route and model reality is mapped against RFC-0083,
2. the highest-risk gaps are identified,
3. implementation slices are ordered,
4. repo-local context points engineers to this document,
5. no runtime behavior or generated contract output is changed.

