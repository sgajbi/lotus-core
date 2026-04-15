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

## Inventory Evidence Used

This pass was based on the current repository state on branch `feat/rfc-0082-boundary-governance`.

The inventory reviewed:

1. downstream route modules under `src/services/query_service/app/routers`,
2. analytics, integration, support, and simulation route modules under
   `src/services/query_control_plane_service/app/routers`,
3. write-ingress route modules under `src/services/ingestion_service/app/routers`,
4. replay, DLQ, ingestion-health, and ingestion-operations routes under
   `src/services/event_replay_service/app/routers`,
5. reconciliation route modules under `src/services/financial_reconciliation_service/app/routers`,
6. SQLAlchemy model/table definitions in `src/libs/portfolio-common/portfolio_common/database_models.py`,
7. DTO and repository usage of temporal, source-lineage, tenant, policy, correlation, and idempotency
   fields across `src`.

The inventory did not execute runtime flows or generated OpenAPI output. Runtime proof starts in later
slices when schemas, route metadata, migrations, or behavior change.

## Severity Model

| Severity | Meaning | Current gaps |
| --- | --- | --- |
| P0 blocker before runtime contract hardening | Without this, later implementation can create incompatible or ambiguous contracts | Temporal vocabulary, route family enforcement |
| P1 blocker before consumer migration | Without this, downstream services can consume unstable or incomplete source shapes | Portfolio reconstruction semantics, restatement/version behavior, source-data product minimum metadata, consumer impact maps |
| P2 blocker before production readiness | Without this, operators and auditors cannot prove data trust or diagnose failures safely | Ingestion evidence bundles, reconciliation evidence bundles, data-quality coverage reports, product SLOs |
| P3 cleanup during touched slices | Important to prevent drift, but not a blocker for the next slice if guarded | Endpoint consolidation watchlist, duplicate convenience routes, inconsistent descriptions |

Slice 1 should address the P0 temporal vocabulary gap first because temporal semantics affect schema
names, DTO documentation, migration planning, source-data product identity, and downstream analytics
repeatability.

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
| `PortfolioAnalyticsReference` | `/integration/portfolios/{portfolio_id}/analytics/reference`, portfolio reference state | Strong baseline | Keep aligned with analytics input product identity, freshness, and evidence metadata |
| `MarketDataWindow` | prices, FX, market/reference integration routes | Partial | Separate operational raw reads from analytics-safe windows |
| `InstrumentReferenceBundle` | instruments, enrichment bulk, taxonomy, lookthrough | Partial | Package reference primitives as a stable bundle contract |
| `BenchmarkAssignment` | benchmark assignment route and table | Strong baseline | Add product-level provenance and version/deprecation rules |
| `BenchmarkConstituentWindow` | benchmark composition window route and table | Strong baseline | Add completeness and observed/ingested timestamp semantics |
| `IndexSeriesWindow` | index price and return series routes and tables | Strong baseline | Standardize freshness, paging, and source lineage |
| `RiskFreeSeriesWindow` | risk-free series route and table | Strong baseline | Standardize source lineage and coverage metadata |
| `ReconciliationEvidenceBundle` | financial reconciliation routes and findings | Partial | Create a consumer-safe evidence product linked to portfolios and source scope |
| `DataQualityCoverageReport` | coverage, readiness, support, and SLO routes | Partial | Define one governed report shape for downstream gating |
| `IngestionEvidenceBundle` | ingestion jobs, failures, replay, DLQ, audit routes | Partial | Define evidence bundle shape across ingestion and replay services |

## Ingestion And Replay Capability Inventory

Current strengths:

1. write-ingress routes exist for transactions, transaction batches, portfolios, portfolio bundles,
   instruments, market prices, FX rates, business dates, benchmark/reference data, uploads, and
   transaction reprocessing,
2. ingestion job, failure, backlog, SLO, operating-band, capacity, saturation, stalled-job, DLQ, replay,
   replay-audit, operations-control, and idempotency diagnostics are exposed through ingestion
   operations routes,
3. job and replay tables exist for ingestion jobs, ingestion job failures, ingestion operations control,
   consumer DLQ events, consumer DLQ replay audit, reprocessing jobs, processed events, and outbox
   events,
4. correlation id, trace id, idempotency key, source system, source batch, and source record fields
   appear in important ingestion and reference paths.

Current gaps:

1. there is no single named `IngestionEvidenceBundle` contract that packages source batch, validation,
   replay, rejection, quarantine, and operator evidence for downstream and audit consumers,
2. accepted, rejected, quarantined, partially accepted, replayed, and repaired states are not yet
   normalized as one business vocabulary across all ingestion surfaces,
3. source timestamp terminology still needs alignment with `observed_at` and `ingested_at`,
4. replay and DLQ evidence is operationally rich but not yet tied consistently to source-data product
   provenance,
5. retention and archival expectations for raw source records, validation reports, and replay audit
   records are not yet explicit.

Required follow-up slice:

1. Slice 4 owns the runtime and contract hardening for ingestion and source lineage.
2. Slice 0 only records the current baseline and keeps implementation out of scope.

## Reconciliation And Data-Quality Capability Inventory

Current strengths:

1. financial reconciliation routes exist for transaction-to-cashflow completeness,
   position-to-valuation consistency, and portfolio-timeseries integrity controls,
2. reconciliation run and finding tables exist,
3. support routes expose reconciliation runs and findings alongside valuation, aggregation, replay,
   lineage, and readiness diagnostics,
4. coverage/readiness routes already provide a useful basis for data-quality and supportability
   signals.

Current gaps:

1. there is no single named `ReconciliationEvidenceBundle` contract that downstream consumers can use
   to decide whether source data is reconciled, unreconciled, partial, stale, blocked, or unknown,
2. reconciliation statuses, finding severities, break ownership, tolerance, age, and resolution state
   need one governed vocabulary,
3. reconciliation evidence is not yet uniformly included in source-data products where data safety
   depends on it,
4. data-quality coverage is present as supportability behavior but not yet formalized as a
   `DataQualityCoverageReport` product,
5. SLOs for freshness, completeness, reconciliation latency, and supportability are not yet tied to
   individual source-data products.

Required follow-up slice:

1. Slice 5 owns the runtime and contract hardening for reconciliation and data quality.
2. Slice 0 only identifies the capability baseline and the contract gaps.

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

## Open Decisions Before Runtime Slices

These decisions should be closed before code-changing slices expand contracts.

| Decision | Why it matters | Owner slice | Blocking level |
| --- | --- | --- | --- |
| Whether `source_timestamp` is renamed, mapped, or documented as legacy while `observed_at` becomes canonical | Prevents reference/market-data contracts from carrying two source-observation concepts | Slice 1 | P0 |
| Whether `booking_date` is introduced as a new persisted field, derived field, or contract-only concept in the first phase | Booking, correction, and transaction ledger semantics depend on it | Slice 1 or Slice 3 | P0 |
| How `restatement_version` is represented in snapshots, exports, and source-data products | Determines deterministic historical analytics and report replay | Slice 3 or Slice 4 | P1 |
| Which route metadata mechanism records RFC-0082 family and RFC-0083 product identity | Needed for route classification tests and OpenAPI governance | Slice 2 | P0 |
| Which evidence statuses become canonical across ingestion, reconciliation, and source-data products | Prevents each service plane from inventing incompatible safety states | Slice 4 or Slice 5 | P1 |
| Whether endpoint consolidation happens by immediate pre-live replacement or short-lived aliases | Impacts consumer migration effort and RFC-0067 no-alias governance | Slice 8 | P3 |

## Non-Goals For Slice 0

Slice 0 intentionally does not:

1. rename fields,
2. change DTOs,
3. change OpenAPI output,
4. add database migrations,
5. move routes between services,
6. introduce compatibility aliases,
7. change consumer behavior,
8. define final SLO targets.

Those are implementation slices and must carry their own validation evidence.

## Implementation Slice Recommendation

This local slice order intentionally matches the master implementation program in RFC-0083.

| Slice | Goal | Primary output |
| --- | --- | --- |
| 0 | Current-state gap analysis | This document and repo context links |
| 1 | Temporal vocabulary and schema policy | Temporal field policy, contract vocabulary updates, schema guard plan |
| 2 | Command/read route classification enforcement | Route family tests and OpenAPI metadata checks aligned to RFC-0082 |
| 3 | Portfolio reconstruction target model | Reconstruction model, holdings/cash/transaction lineage, deterministic snapshot identity |
| 4 | Ingestion and source-lineage hardening | Source batch identity, validation report contract, partial rejection, replay, DLQ/repair posture |
| 5 | Reconciliation and data-quality model | Reconciliation status vocabulary, break model, data-quality coverage contract |
| 6 | Source-data product catalog implementation | Priority source-data products, analytics input alignment, paging/export behavior |
| 7 | Market/reference/benchmark product hardening | Market, FX, instrument, benchmark, index, and risk-free product contracts |
| 8 | Endpoint consolidation | Watchlist cleanup, migrations, aliases/deprecations, consumer migration notes |
| 9 | Security, tenancy, retention, and entitlement | Uniform access, policy, audit, and lifecycle controls |
| 10 | Eventing and supportability hardening | Event family definitions, observability posture, supportability APIs, operator diagnostics |
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

## Acceptance Evidence By Implementation Slice

| Slice | Acceptance evidence |
| --- | --- |
| 1 | Temporal vocabulary note, ambiguous temporal field inventory, keep/rename/map/legacy decision for each ambiguous field, guard plan, and validation plan for any schema or OpenAPI change |
| 2 | Route classification inventory, route metadata or OpenAPI evidence for RFC-0082 family coverage, failing test path for unclassified downstream routes, and vocabulary/no-alias evidence where affected |
| 3 | Portfolio reconstruction model, deterministic snapshot identity rule, holdings/cash/transaction lineage requirements, restatement decision record, and targeted tests if runtime behavior changes |
| 4 | Source batch identity model, validation report contract, partial rejection behavior, replay/DLQ evidence contract, retention note, and ingestion/replay test evidence for runtime changes |
| 5 | Reconciliation status vocabulary, break/finding model, data-quality coverage contract, source-data product supportability field requirements, and reconciliation/supportability test evidence for runtime changes |
| 6 | Source-data product catalog, product owners and versions, required metadata template, paging/export rules, consumer map updates, and performance/risk contract evidence where affected |
| 7 | Market/reference/benchmark alignment note, observed/ingested timestamp decision, freshness/completeness diagnostics, and downstream analytics input evidence where affected |
| 8 | Endpoint watchlist disposition, deprecation or removal notes, affected-consumer migration evidence, RFC-0067 no-alias evidence, and platform proof when gateway/workbench behavior changes |
| 9 | Tenant/entitlement/support access classification, audit and retention requirements, PII/client-sensitive field notes where applicable, and security/entitlement test evidence for runtime changes |
| 10 | Event family definitions, event schema governance, supportability API posture, operator diagnostic evidence, and event/supportability tests where runtime behavior changes |
| 11 | Final route inventory, final source-data product catalog, final temporal-field inventory, final deprecation list, downstream conformance proof, and updated platform/repo context docs |

## Slice 1 Ready Checklist

Slice 1 can start when the implementer has this document, RFC-0083, and the RFC-0082 route inventory
open and agrees to keep the first runtime-adjacent change limited to temporal vocabulary and schema
policy.

Slice 1 should produce:

1. a canonical temporal vocabulary note in `lotus-core`,
2. an inventory of ambiguous current temporal fields and whether each is keep, rename, map, or
   document-as-legacy,
3. route/schema guidance for new DTOs,
4. a practical guard plan for preventing new generic date fields in downstream-facing contracts,
5. a validation plan for any OpenAPI or DTO changes.

Slice 1 should not yet consolidate endpoint families, redesign ingestion, or introduce broad
source-data product DTO changes. Those follow after temporal semantics are stable.

## Slice 1 Completion Note

Slice 1 policy output is now recorded in:

- `docs/standards/temporal-vocabulary.md`

That standard defines canonical temporal terms, current-field decisions, `source_timestamp` legacy
handling, `booking_date` target handling, `restatement_version` target handling, and the temporal guard
plan. It does not change runtime behavior, schemas, generated OpenAPI, or persistence.

## Slice 2 Completion Note

Slice 2 route classification enforcement is recorded in:

- `docs/standards/route-contract-family-registry.json`
- `scripts/route_contract_family_guard.py`
- `tests/unit/scripts/test_route_contract_family_guard.py`

The guard parses active FastAPI router decorators and fails when a route is added, removed, or renamed
without a matching RFC-0082 family registry update. It does not change runtime behavior, schemas,
generated OpenAPI, or persistence.

## Slice 3 Completion Note

Slice 3 portfolio reconstruction target modeling is recorded in:

- `docs/architecture/RFC-0083-portfolio-reconstruction-target-model.md`
- `src/libs/portfolio-common/portfolio_common/reconstruction_identity.py`
- `tests/unit/libs/portfolio-common/test_reconstruction_identity.py`

The model defines the target reconstruction scope, holdings/cash/transaction lineage requirements,
snapshot identity rules, and the current restatement decision. The helper provides an executable
deterministic identity rule for future source-data product wiring. This slice does not change runtime
behavior, schemas, generated OpenAPI, persistence, or downstream contract shape.

## Slice 4 Completion Note

Slice 4 ingestion source-lineage target modeling is recorded in:

- `docs/architecture/RFC-0083-ingestion-source-lineage-target-model.md`
- `src/libs/portfolio-common/portfolio_common/ingestion_evidence.py`
- `tests/unit/libs/portfolio-common/test_ingestion_evidence.py`

The model defines source batch identity, validation report status vocabulary, partial rejection rules,
replay/DLQ evidence fields, and retention/repair posture. The helper provides executable source-batch
fingerprinting and partial outcome classification for future ingestion evidence DTO wiring. This slice
does not change runtime behavior, schemas, generated OpenAPI, persistence, or downstream contract shape.

## Slice 5 Completion Note

Slice 5 reconciliation and data-quality target modeling is recorded in:

- `docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md`
- `src/libs/portfolio-common/portfolio_common/reconciliation_quality.py`
- `tests/unit/libs/portfolio-common/test_reconciliation_quality.py`

The model defines the target reconciliation status vocabulary, break model, data-quality coverage
contract, and source-data product supportability field requirements. The helper provides executable
status classification for future evidence DTO wiring. This slice does not change runtime behavior,
schemas, generated OpenAPI, persistence, or downstream contract shape.

## Slice 6 Completion Note

Slice 6 source-data product catalog modeling is recorded in:

- `docs/architecture/RFC-0083-source-data-product-catalog.md`
- `src/libs/portfolio-common/portfolio_common/source_data_products.py`
- `tests/unit/libs/portfolio-common/test_source_data_products.py`
- `scripts/source_data_product_contract_guard.py`
- `tests/unit/scripts/test_source_data_product_contract_guard.py`

The catalog defines priority source-data product names, versions, route-family ownership, serving
plane, consumers, current route mappings, required supportability metadata, paging/export disposition,
and convenience shapes to consolidate. The helper validates duplicate product names, duplicate route
ownership, required metadata, and consumer product lookup. The contract guard validates that every
catalog route exposes matching `x-lotus-source-data-product` OpenAPI metadata and that every catalog
route response model exposes matching `product_name` and `product_version` DTO-envelope defaults.
This slice remains additive: it does not change request semantics, persistence, generated events, or
calculation behavior.

## Slice 7 Completion Note

Slice 7 market and reference data target modeling is recorded in:

- `docs/architecture/RFC-0083-market-reference-data-target-model.md`
- `src/libs/portfolio-common/portfolio_common/market_reference_quality.py`
- `tests/unit/libs/portfolio-common/test_market_reference_quality.py`

The model defines instrument/reference, market-data, benchmark, index, and risk-free product
alignment; maps legacy `source_timestamp` to canonical `observed_at`; and standardizes market and
reference data point quality, freshness, and coverage classification. This slice does not change
runtime behavior, schemas, generated OpenAPI, persistence, or downstream contract shape.

## Slice 8 Completion Note

Slice 8 endpoint consolidation disposition is recorded in:

- `docs/architecture/RFC-0083-endpoint-consolidation-disposition.md`
- `src/services/query_service/app/routers/reporting.py`
- `tests/integration/services/query_service/test_main_app.py`

The slice marks selected pre-live reporting convenience routes as deprecated in OpenAPI and points
them to their RFC-0083 target source-data products. It keeps runtime handlers and route-family
classification stable until affected consumers migrate. Route removal remains gated by consumer
evidence, RFC-0067 no-alias governance, route-registry updates, and platform proof where gateway or
Workbench behavior changes.

## Slice 9 Completion Note

Slice 9 security, tenancy, and lifecycle target modeling is recorded in:

- `docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md`
- `src/libs/portfolio-common/portfolio_common/source_data_security.py`
- `tests/unit/libs/portfolio-common/test_source_data_security.py`
- `src/libs/portfolio-common/portfolio_common/enterprise_readiness.py`
- `tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py`
- `src/services/query_service/app/enterprise_readiness.py`
- `src/services/query_control_plane_service/app/enterprise_readiness.py`

The model defines source-data product security profiles covering tenant scoping, entitlement scoping,
access classification, sensitivity classification, retention requirement, audit requirement,
PII/client-sensitive fields, and operator-only evidence posture. The helper validates that every
source-data product has a profile and emits `x-lotus-source-data-security` OpenAPI metadata for
catalog-backed routes. Shared enterprise-readiness runtime support now removes duplicated
query-service and query-control-plane write authorization, capability-rule, policy-header, write
audit, opt-in read audit, and opt-in read authorization middleware logic while preserving
service-local settings and wrapper functions. Security profile validation now also prevents operator-only products from being classified
outside control-plane and policy route families and constrains business, system, and operator access
classes, audit requirements, and sensitivity-driven retention requirements to their governed
RFC-0082/RFC-0083 lanes. This slice does not introduce new entitlement policy semantics, persistence
changes, or downstream response payload shape changes.

## Slice 10 Completion Note

Slice 10 eventing and supportability target modeling is recorded in:

- `docs/architecture/RFC-0083-eventing-supportability-target-model.md`
- `src/libs/portfolio-common/portfolio_common/event_supportability.py`
- `src/libs/portfolio-common/portfolio_common/events.py`
- `tests/unit/libs/portfolio-common/test_event_supportability.py`
- `scripts/event_runtime_contract_guard.py`
- `tests/unit/scripts/test_event_runtime_contract_guard.py`
- `src/libs/portfolio-common/portfolio_common/outbox_repository.py`
- `tests/unit/libs/portfolio-common/test_outbox_repository.py`

The model defines event family governance, event schema-governance requirements, supportability
surface posture, operator-only diagnostics, and evidence bundle linkage. The helper validates event
family definitions, schema model bindings, required idempotency/correlation/schema version posture,
operator supportability surfaces, operator-only security profile bindings for support evidence, and
actual outbox `event_type`/topic alignment against runtime emissions. `OutboxRepository` now
centrally enriches payloads with `event_type`, `schema_version`, and
`correlation_id` supportability metadata and rejects conflicting caller-supplied metadata. Shared event
models inherit from `CoreEventModel`, which explicitly ignores envelope metadata that is not part of a
specific domain payload. This slice does not change Kafka topics, generated OpenAPI, persistence schema,
or downstream contract shape.

## Slice 11 Completion Note

Slice 11 production-readiness closure is recorded in:

- `docs/architecture/RFC-0083-production-readiness-closure.md`
- `docs/standards/rfc-0083-implementation-ledger.json`
- `scripts/rfc0083_closure_guard.py`
- `tests/unit/scripts/test_rfc0083_closure_guard.py`

The closure ledger records the implemented RFC-0083 target-model artifacts for every slice and the
closure guard verifies that every listed artifact exists. The ledger intentionally records
`runtimeProductionStatus` as `not-production-closed`; full runtime closure still requires PR Merge
Gate evidence, affected consumer proof, and platform validation where canonical flows depend on core
behavior.

## Slice 0 Acceptance

Slice 0 is complete when:

1. the current route and model reality is mapped against RFC-0083,
2. the highest-risk gaps are identified,
3. implementation slices are ordered,
4. repo-local context points engineers to this document,
5. no runtime behavior or generated contract output is changed.
