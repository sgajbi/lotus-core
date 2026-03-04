# RFC 063 - Lotus-Core Stateful Analytics Input Contracts for Lotus-Performance

## Status
Proposed (Implementation Ready, Delta-Oriented)

## Date
2026-03-01

## Owners
- lotus-core: canonical stateful data provider
- lotus-performance: analytics computation owner
- lotus-platform: governance owner (RFC-0067 compliance)

## 1. Executive Summary
This RFC defines the lotus-core contracts required by lotus-performance to compute TWR, MWR, contribution, and attribution in stateful mode with PB/WM-grade rigor.

Design principles:
1. lotus-core serves canonical state and lineage-complete raw inputs.
2. lotus-performance performs all analytics calculations.
3. Instrument enrichment is provided as a separate contract, not redundantly embedded in timeseries payloads.
4. APIs are streamable and chunkable for long horizons and large portfolios.
5. Naming, OpenAPI, and vocabulary are fully governed by RFC-0067.

## 2. Goals
1. Provide an implementation-ready contract baseline for stateful analytics inputs.
2. Reuse existing lotus-core contracts wherever already compliant.
3. Introduce only missing/partial capabilities with deterministic semantics.
4. Ensure high-volume operability: paging, chunking, async export, and stream-friendly delivery.
5. Align canonical vocabulary to PB/WM conventions and eliminate ambiguous field names.

## 3. Non-Goals
1. Implementing analytics formulas in lotus-core.
2. Defining lotus-performance output payloads or UI-facing contracts.
3. Replacing RFC-062 benchmark and risk-free contract ownership.

## 3.1 Assumptions and Fixed Decisions
1. `as_of_date` is a point-in-time cutoff, not a window end substitute.
2. `valuation_date` is business-date keyed and must be timezone-neutral (`date`).
3. Numeric monetary/rate/weight fields are represented as decimal-safe contract values (string-formatted decimals in JSON transport).
4. Instrument enrichment remains a separate join contract and is never duplicated inline in timeseries rows.

## 4. Current Capability Assessment

### 4.1 Existing and Reusable
1. `POST /integration/portfolios/{portfolio_id}/core-snapshot`
2. `POST /integration/instruments/enrichment-bulk`
3. RFC-062 query surfaces:
   - benchmark assignment, benchmark/index catalogs and definitions
   - benchmark/index/risk-free series
   - taxonomy and coverage diagnostics

### 4.2 Partial Gaps
1. No dedicated long-horizon portfolio valuation/cashflow timeseries contract.
2. No dedicated long-horizon position valuation timeseries contract.
3. Core snapshot is fit for snapshots but not optimal as the single high-volume historical feed.
4. Streaming and asynchronous extraction controls are not defined as first-class integration contract behavior.

### 4.3 Missing
1. Canonical async export job pattern for analytics datasets.
2. Standardized chunk token contract for large timeseries traversal.
3. Explicit data quality summary envelope for portfolio/position timeseries endpoints.

## 5. Target Contract Architecture

### 5.1 Contract Families
1. `state_timeseries` contracts:
   - portfolio valuation and cashflow series
   - position valuation and cashflow series
2. `state_reference` contracts:
   - instrument enrichment (already present, reused)
   - classification taxonomy (RFC-062, reused)
   - portfolio metadata endpoint (new lightweight reference contract)
3. `state_export` contracts:
   - async export job create/status/result for very large ranges

### 5.2 Non-Redundant Enrichment Rule
1. Timeseries responses include `security_id`, `position_id`, and dimension keys only.
2. Issuer/instrument enrichment is resolved separately by `POST /integration/instruments/enrichment-bulk`.
3. Consumers join by `security_id` (or `issuer_id` where relevant).

## 6. API Design (Normative)

### 6.1 Portfolio Analytics Timeseries (New)
1. `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`

Request:
1. `as_of_date`
2. `window`: `start_date`, `end_date` or `period`
3. `reporting_currency` (optional)
4. `frequency` (`daily`, future-safe for `weekly`, `monthly`)
5. `consumer_system`
6. `page`:
   - `page_size`
   - `page_token`

Response:
1. metadata:
   - `portfolio_id`, `portfolio_currency`, `reporting_currency`
   - `portfolio_open_date`, `portfolio_close_date`, `performance_end_date`
   - `resolved_window`, `frequency`, `contract_version`, `lineage`
2. observations:
   - `valuation_date`
   - `beginning_market_value`
   - `ending_market_value`
   - `cash_flows[]`:
     - `amount`
     - `timing` (`bod`, `eod`)
     - `cash_flow_type` (`external_flow`, `fee`, `tax`, `transfer`, `income`, `other`)
3. diagnostics:
   - `quality_status_distribution`
   - `missing_dates_count`
   - `stale_points_count`
4. paging:
   - `next_page_token`

### 6.2 Position Analytics Timeseries (New)
1. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`

Request:
1. same window controls as portfolio timeseries
2. `dimensions[]` (for example `asset_class`, `sector`, `region`, `country`)
3. `filters` (optional):
   - `security_ids[]`
   - `position_ids[]`
   - `dimension_filters`
4. `reporting_currency` (optional)
5. `consumer_system`
6. paging controls

Response:
1. metadata:
   - `portfolio_id`, `portfolio_currency`, `reporting_currency`
   - `resolved_window`, `frequency`, `contract_version`, `lineage`
2. rows:
   - identifiers: `position_id`, `security_id`
   - selected dimensions as canonical labels
   - `valuation_date`
   - `beginning_market_value_position_currency`
   - `ending_market_value_position_currency`
   - `beginning_market_value_portfolio_currency`
   - `ending_market_value_portfolio_currency`
   - reporting-currency values when requested
   - optional `cash_flows[]` using canonical structure
3. diagnostics and paging as above

### 6.3 Portfolio Metadata Reference (New Lightweight)
1. `POST /integration/portfolios/{portfolio_id}/analytics/reference`

Purpose:
1. Return static/slow-moving portfolio metadata needed by analytics engines without large payload duplication.

### 6.4 Instrument Enrichment (Reuse Existing)
1. `POST /integration/instruments/enrichment-bulk`
2. No enrichment fields duplicated in timeseries responses.

### 6.5 Benchmark and Risk-Free (Reuse RFC-062)
1. No new benchmark/risk-free endpoints in RFC-063.
2. RFC-062 remains authoritative.

### 6.6 Async Export Contracts (New)
1. `POST /integration/exports/analytics-timeseries/jobs`
2. `GET /integration/exports/analytics-timeseries/jobs/{job_id}`
3. `GET /integration/exports/analytics-timeseries/jobs/{job_id}/result`

Purpose:
1. Handle large requests safely outside synchronous request time limits.
2. Result format supports NDJSON and compressed JSON (`gzip`).

### 6.7 API Inventory Mapping (Decision)
1. Reuse unchanged:
   - `POST /integration/instruments/enrichment-bulk`
   - RFC-062 benchmark/risk-free endpoints
2. Extend behavior (non-breaking):
   - `POST /integration/portfolios/{portfolio_id}/core-snapshot` for shared lineage/policy semantics only
3. New contracts:
   - `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
   - `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`
   - `POST /integration/portfolios/{portfolio_id}/analytics/reference`
   - export jobs endpoints in section 6.6

## 7. Streamability and High-Volume Behavior
1. Synchronous endpoints must support deterministic pagination:
   - portfolio-timeseries: `(valuation_date, portfolio_id)`
   - position-timeseries: `(valuation_date, position_id, security_id)`
2. Support `Accept: application/x-ndjson` for streamable responses where payload size is large.
3. Async export is required when estimated payload exceeds configured threshold.
4. Response envelopes include dataset cardinality estimates and page cursor metadata.
5. Idempotent retrieval for same request fingerprint and dataset version.
6. `page_token` must be opaque, signed, and stable for a given dataset version.
7. `page_size` must be bounded with platform defaults and max limits enforced server-side.

## 8. Quant and Analytics Data Requirements
The following fields are mandatory additions for robust analytics operations:
1. `valuation_status` per observation (`final`, `provisional`, `restated`)
2. `price_staleness_days` (or equivalent staleness indicator)
3. `fx_rate_source` and `fx_rate_timestamp` when reporting currency conversion is applied
4. `data_version` and `source_timestamp` lineage at dataset level
5. explicit `calendar_id` used for the resolved window
6. `missing_observation_policy` metadata (`strict`, `forward_fill`, `skip`)

These are metadata fields only, not analytics outputs.

### 8.1 Precision and Rounding Requirements
1. No binary floating-point transport for monetary/rate fields in APIs.
2. Decimal precision/scale must be documented per field in OpenAPI descriptions.
3. Rounding policy metadata must be explicit when server-side normalization is applied.
4. Cross-currency converted values must carry FX lineage (`fx_rate_source`, `fx_rate_timestamp`, and rate identifier when available).

## 9. Naming and PB/WM Standards
1. Canonical snake_case only.
2. One concept, one canonical term, no semantic aliases.
3. Field names must express monetary context:
   - `*_position_currency`, `*_portfolio_currency`, `*_reporting_currency`
4. Abbreviations are avoided unless industry standard and unambiguous (`twr`, `mwr` allowed in endpoint context, not as ambiguous field names).
5. Vocabulary updates are mandatory in the same PR cycle per RFC-0067.

## 10. Error and Quality Semantics
Standard error classes:
1. `INVALID_REQUEST`
2. `RESOURCE_NOT_FOUND`
3. `INSUFFICIENT_DATA`
4. `SOURCE_UNAVAILABLE`
5. `UNSUPPORTED_CONFIGURATION`
6. `CONTRACT_VIOLATION_UPSTREAM`

Quality signaling:
1. `quality_status_distribution`
2. `missing_dates_count` and sample
3. `stale_points_count`
4. reproducible lineage and request fingerprint

## 11. Security and Access Model
1. Service-to-service access only for analytics contracts.
2. Optional tenant policy filtering via `consumer_system` and `tenant_id`.
3. Full correlation/request/trace propagation required.

## 11.1 Observability Requirements
1. Emit endpoint-level latency, payload-size, and page-depth metrics for all new analytics contracts.
2. Emit export job lifecycle metrics (`created`, `running`, `completed`, `failed`, `expired`).
3. Log request fingerprint, dataset version, and pagination cursor metadata at info/debug levels with correlation IDs.
4. Add contract-specific health checks for export worker and storage readiness.

## 12. Implementation Plan (Incremental Slices)
1. Slice 0: Gap audit against current `core-snapshot` and RFC-062 contracts.
2. Slice 1: Portfolio timeseries endpoint + tests + OpenAPI + vocab sync.
3. Slice 2: Position timeseries endpoint + dimension/filter semantics.
4. Slice 3: Async export contracts + operational diagnostics.
5. Slice 4: Performance hardening (streaming mode, cursor determinism, large-range tests).
6. Slice 5: Cross-repo contract tests with lotus-performance.

## 13. Acceptance Criteria
1. Existing reusable contracts remain backward-compatible.
2. New timeseries contracts cover TWR/MWR/contribution/attribution input requirements.
3. Instrument enrichment is separated and non-redundant by design.
4. Large-window requests succeed using paging or async export without direct DB dependency.
5. RFC-0067 gates pass:
   - OpenAPI quality
   - inventory generation
   - platform catalog validation
6. Contract tests between lotus-core and lotus-performance are green.
7. Performance acceptance:
   - deterministic paging validated on large windows
   - export jobs validated for restart/retry and idempotent retrieval
8. No enrichment duplication in timeseries payloads; enrichment joins are verified via separate contract tests.
