# RFC 064 - Benchmark Exposure History and Position Timeseries Contract for lotus-risk Historical Attribution

## Status
Proposed (Implementation Ready)

## Date
2026-03-01

## Owners
- lotus-core: canonical domain and master-data provider
- lotus-risk: stateful attribution consumer
- lotus-platform: governance owner (RFC-0067)

## 1. Summary
`lotus-risk` historical attribution stateful mode requires canonical, time-aligned exposure history from `lotus-core`.
Current position timeseries capability is usable for total risk attribution by grouping dimension, but full active risk attribution also needs benchmark exposure history in the same contract family.

This RFC defines the required lotus-core enhancements and acceptance criteria.

## 2. Goals
1. Provide deterministic portfolio exposure history for risk attribution engines.
2. Add benchmark exposure history contract to enable active risk decomposition.
3. Preserve separation of concerns:
- lotus-core owns canonical state and reference data.
- lotus-risk owns attribution calculations.
4. Enforce RFC-0067 naming, documentation, and vocabulary compliance.

## 3. Non-Goals
1. Implement attribution formulas in lotus-core.
2. Return pre-computed risk attribution outputs.
3. Replace lotus-performance return-series responsibilities.

## 4. Existing Reuse
1. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`
2. `POST /integration/instruments/enrichment-bulk`

These remain authoritative and are reused.

## 5. Required Contracts

### 5.1 Position Timeseries (Portfolio Exposures)
Endpoint:
- `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`

Required request fields:
1. `as_of_date`
2. `window.start_date`, `window.end_date`
3. `frequency` (`daily` in v1)
4. `dimensions[]` (supports at least `sector`, `asset_class`)
5. `reporting_currency` optional
6. `consumer_system`
7. `page.page_size`, `page.page_token`

Required response fields per row:
1. `valuation_date`
2. `security_id`
3. `ending_market_value_reporting_currency` and/or `ending_market_value_portfolio_currency`
4. `dimensions`

Required behavior:
1. Deterministic ordering and pagination.
2. ISO date fields only.
3. Decimal-safe numeric transport.

### 5.2 Benchmark Exposure History (New Required Capability)
Endpoint (new):
- `POST /integration/benchmarks/{benchmark_id}/analytics/exposure-timeseries`

Purpose:
- supply benchmark constituent/grouped exposure history over the same window used for portfolio attribution.

Required request fields:
1. `as_of_date`
2. `window.start_date`, `window.end_date`
3. `frequency`
4. `dimensions[]` (same taxonomy semantics as portfolio endpoint)
5. `reporting_currency` optional
6. `consumer_system`
7. `page.page_size`, `page.page_token`

Required response fields:
1. `rows[]` with:
- `valuation_date`
- `benchmark_id`
- `security_id` (or canonical synthetic key when index constituent id is unavailable)
- `ending_weight` (decimal)
- `dimensions`
2. `page.next_page_token`
3. `metadata.contract_version`

Required behavior:
1. Same dimension taxonomy and naming as portfolio timeseries.
2. Deterministic row ordering and stable pagination.
3. Coverage flags for missing constituents/dates.

### 5.3 Instrument Enrichment (Reuse)
Endpoint:
- `POST /integration/instruments/enrichment-bulk`

Must include:
1. `issuer_id`
2. `issuer_name`
3. `ultimate_parent_issuer_id`
4. `ultimate_parent_issuer_name`

## 6. Data and Model Semantics
1. One concept, one canonical field name across endpoints.
2. Grouping dimensions used by lotus-risk v1:
- `POSITION`
- `SECTOR`
- `ASSET_CLASS`
- `ISSUER` (via enrichment)
3. Exposure construction must support complete daily normalization by valuation date.

## 7. Error Model and Diagnostics
Use standard Lotus envelope with deterministic codes:
1. `INVALID_REQUEST`
2. `RESOURCE_NOT_FOUND`
3. `INSUFFICIENT_DATA`
4. `SOURCE_UNAVAILABLE`
5. `UNSUPPORTED_CONFIGURATION`

Diagnostics expected:
1. coverage summary by date range
2. missing-date and missing-constituent indicators
3. correlation ID propagation

## 8. Testing Requirements
1. Contract tests:
- schema shape
- required field presence
- pagination determinism
2. Characterization tests:
- fixed fixtures for exposures and dimensions
- stable row ordering and totals by date
3. Integration tests:
- instrument enrichment join compatibility for issuer grouping
- benchmark exposure retrieval behavior

## 9. Governance Requirements
1. OpenAPI descriptions and examples for every field.
2. API vocabulary inventory entries for any new fields.
3. No aliases; canonical snake_case only.
4. Backward compatibility preserved for existing consumers.

## 10. Acceptance Criteria
1. lotus-risk stateful `TOTAL_RISK` attribution consumes position-timeseries without contract gaps.
2. lotus-risk stateful `ACTIVE_RISK` attribution is enabled by benchmark exposure-timeseries availability.
3. All new/updated fields pass RFC-0067 documentation and vocabulary quality gates.
