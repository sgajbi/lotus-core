# RFC 062 - Benchmark and Risk-Free Reference Data Contract for Downstream Analytics

## Status
Implemented (lotus-core query + ingestion contracts live)

## Date
2026-03-01

## Owners
- lotus-core: assignment + reference data contract owner
- lotus-performance: benchmark/risk-free analytics computation owner
- lotus-risk: downstream analytics consumer (via lotus-performance)

## Related RFCs
- RFC 049 - Core snapshot analytics de-ownership
- RFC 057 - Directory reorganization and ownership boundaries
- RFC 058 - Core snapshot contract
- RFC-0067 (lotus-platform) - API vocabulary and OpenAPI governance

## 1. Executive Summary
This RFC defines the **authoritative Lotus-Core contract** for benchmark and risk-free reference inputs required by lotus-performance.

Core principle:
1. lotus-core owns **assignment, definition, and raw reference series serving**.
2. lotus-performance owns **all derived calculations** (benchmark returns, excess returns, attribution inputs, compounding, annualization, linking).

This keeps service ownership clean while giving lotus-performance deterministic, lineage-complete, PB/WM-grade inputs.

## 2. Problem Statement
Without a formal reference-data and assignment contract, downstream analytics can diverge in:
1. benchmark assignment resolution by effective date
2. composite weight interpretation and rebalance timing
3. price/return convention handling (PRI/TRI)
4. risk-free rate convention interpretation (annualized vs period return)
5. FX normalization and calendar intersection logic
6. replay/restate reproducibility

The result is analytics drift, reconciliation pain, and weak operational support.

## 3. Goals
1. Provide deterministic, API-first contracts for benchmark assignment and raw reference data.
2. Preserve strict ownership boundary: no analytics computation in lotus-core.
3. Support both single-index and composite benchmark structures.
4. Treat benchmark-to-portfolio links, benchmark compositions, and reference series as first-class time-series with full history preservation.
5. Provide operational APIs sufficient for ingestion support and monitoring without direct DB access.
6. Align naming and documentation with RFC-0067 (canonical snake_case, no aliases, WM/PB terminology).
7. Support explicit benchmark/index master sets and raw vendor-provided price/return series contracts for downstream quant services.
8. Expose canonical classification attributes (for example asset class, sector, region, style, theme) so lotus-performance attribution can use shared platform vocabulary.

## 4. Non-Goals
1. Calculating benchmark return series in lotus-core.
2. Calculating excess return, tracking error, information ratio, alpha, or attribution in lotus-core.
3. Delivering consumer-specific report formats in lotus-core.
4. Building lotus-risk direct contracts that bypass lotus-performance ownership.

## 5. Architecture and Ownership Decision

### 5.1 Ownership Matrix
1. lotus-core:
 - benchmark assignment resolution
 - benchmark master and composition definitions
 - raw benchmark component series and risk-free series serving
 - data quality, lineage, and effective-dated contract guarantees
2. lotus-performance:
 - benchmark and risk-free transformation/calculation
 - all derived analytics outputs
 - analytics policy application (linking, annualization, geometric/arith rules)

### 5.2 Boundary Rule (Normative)
lotus-core must only return **raw, convention-labeled, quality-scored inputs**. Any field that is a derived analytics output is out of scope.

### 5.3 Service Exposure Rule (Normative)
1. All RFC-62 query contracts under `/integration/*` are exposed by `lotus-core` query service.
2. `lotus-performance` must consume RFC-62 data only through these query service APIs.
3. No direct database access is allowed for benchmark/index/risk-free acquisition.
4. Ingestion endpoints may write/update data, but downstream reads for analytics must resolve through query service contracts.
5. Query service endpoints must return contract version + lineage metadata on every response.

## 6. Canonical Domain Model (Normative)

### 6.1 Benchmark Assignment
- portfolio_id
- benchmark_id
- effective_from
- effective_to
- assignment_source
- assignment_status
- policy_pack_id
- source_system
- assignment_recorded_at
- assignment_version

Note:
- benchmark assignment is a historical time-series relation in storage; superseded links are retained and queryable.

### 6.2 Benchmark Master
- benchmark_id
- benchmark_name
- benchmark_type (`single_index` | `composite`)
- benchmark_currency
- return_convention (`price_return_index` | `total_return_index`)
- benchmark_status
- benchmark_family
- benchmark_provider
- rebalance_frequency
- classification_set_id
- classification_labels (canonical map, for example `asset_class`, `sector`, `region`, `style`)

### 6.3 Index Master
- index_id
- index_name
- index_currency
- index_type
- index_status
- index_provider
- index_market
- classification_set_id
- classification_labels (canonical map, for example `asset_class`, `sector`, `region`, `style`, `theme`)

### 6.4 Benchmark Composition Series Point
- benchmark_id
- index_id
- composition_effective_from
- composition_effective_to
- composition_weight
- rebalance_event_id
- source_timestamp
- source_vendor
- source_record_id
- quality_status

### 6.5 Index Price Series Point
- series_id
- index_id
- series_date
- index_price
- series_currency
- value_convention
- source_timestamp
- source_vendor
- source_record_id
- quality_status

### 6.6 Index Return Series Point (Raw Vendor-Provided)
- series_id
- index_id
- series_date
- index_return
- return_period
- return_convention
- series_currency
- source_timestamp
- source_vendor
- source_record_id
- quality_status

### 6.7 Benchmark Return Series Point (Raw Vendor-Provided)
- series_id
- benchmark_id
- series_date
- benchmark_return
- return_period
- return_convention
- series_currency
- source_timestamp
- source_vendor
- source_record_id
- quality_status

### 6.8 Risk-Free Reference Series Point
- series_id
- risk_free_curve_id
- series_date
- value
- value_convention (`annualized_rate` | `period_return`)
- day_count_convention
- compounding_convention
- series_currency
- source_timestamp
- source_vendor
- source_record_id
- quality_status

## 7. API Contract - Query Surfaces (Normative)
All endpoints in this section are query service endpoints intended for downstream service-to-service consumption, including lotus-performance.

### 7.1 Resolve Portfolio Benchmark Assignment
- `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`

Request:
- `as_of_date` (required)
- `reporting_currency` (optional)
- `policy_context` (optional: tenant_id, policy_pack_id)

Response:
- assignment metadata + contract/version/lineage
- deterministic single match or explicit conflict error

### 7.2 Fetch Benchmark Definition
- `POST /integration/benchmarks/{benchmark_id}/definition`

Request:
- `as_of_date` (required)

Response:
- single-index or composite definition effective on date
- components + weights + rebalance metadata
- explicit return convention

### 7.3 Fetch Benchmark Master Set
- `POST /integration/benchmarks/catalog`

Request:
- `as_of_date` (required)
- `filters` (optional: benchmark_type, benchmark_currency, benchmark_status)

Response:
- benchmark master records active/effective on date

### 7.4 Fetch Index Master Set
- `POST /integration/indices/catalog`

Request:
- `as_of_date` (required)
- `filters` (optional: index_currency, index_type, index_status)

Response:
- index master records active/effective on date
- includes canonical classification attributes and classification metadata version

### 7.4.1 Fetch Classification Taxonomy (Optional but Recommended)
- `POST /integration/reference/classification-taxonomy`

Request:
- `as_of_date` (required)
- `taxonomy_scope` (optional: `index`, `benchmark`, `portfolio`)

Response:
- canonical classification dimensions
- allowed values/reference codes per dimension
- taxonomy version and effective dating

### 7.5 Fetch Benchmark Market Series Inputs
- `POST /integration/benchmarks/{benchmark_id}/market-series`

Request:
- `as_of_date` (required)
- `window` (required)
- `frequency` (required)
- `target_currency` (optional)
- `series_fields` (required subset of: `index_price`, `index_return`, `benchmark_return`, `component_weight`, `fx_rate`)

Response:
- per-component series points
- resolved window and calendar
- quality summary
- full lineage block

### 7.6 Fetch Index Price Series Inputs
- `POST /integration/indices/{index_id}/price-series`

Request:
- `as_of_date` (required)
- `window` (required)
- `frequency` (required)
- `target_currency` (optional)

Response:
- raw index price points + lineage + quality summary

### 7.7 Fetch Index Return Series Inputs (Raw)
- `POST /integration/indices/{index_id}/return-series`

Request:
- `as_of_date` (required)
- `window` (required)
- `frequency` (required)

Response:
- raw index return points + convention labels + lineage + quality summary

### 7.8 Fetch Benchmark Return Series Inputs (Raw)
- `POST /integration/benchmarks/{benchmark_id}/return-series`

Request:
- `as_of_date` (required)
- `window` (required)
- `frequency` (required)

Response:
- raw benchmark return points + convention labels + lineage + quality summary

### 7.9 Fetch Risk-Free Series Inputs
- `POST /integration/reference/risk-free-series`

Request:
- `as_of_date` (required)
- `window` (required)
- `frequency` (required)
- `currency` (required)
- `series_mode` (`annualized_rate_series` | `return_series`)

Response:
- raw series points only
- explicit convention labels
- resolved window/calendar/quality/lineage

## 8. API Contract - Ingestion Surfaces (Normative)

### 8.1 Benchmark Assignment Ingestion
- `POST /ingest/benchmark-assignments`

### 8.2 Benchmark Definition Ingestion
- `POST /ingest/benchmark-definitions`

### 8.3 Benchmark Composition Series Ingestion
- `POST /ingest/benchmark-compositions`

### 8.4 Index Master Ingestion
- `POST /ingest/indices`

### 8.4.1 Classification Taxonomy Ingestion (Optional but Recommended)
- `POST /ingest/reference/classification-taxonomy`

### 8.5 Index Price Series Ingestion
- `POST /ingest/index-price-series`

### 8.6 Index Return Series Ingestion (Raw)
- `POST /ingest/index-return-series`

### 8.7 Benchmark Return Series Ingestion (Raw)
- `POST /ingest/benchmark-return-series`

### 8.8 Risk-Free Series Ingestion
- `POST /ingest/risk-free-series`

All ingestion endpoints must:
1. support idempotency
2. persist durable ingestion job state
3. emit canonical event lineage
4. fail deterministically with typed reason codes

## 9. Operational APIs (Required)

### 9.1 Reference Data Coverage APIs
1. `POST /integration/benchmarks/{benchmark_id}/coverage`
2. `POST /integration/reference/risk-free-series/coverage`

Coverage response must include:
- observed date range
- expected date range (from request policy)
- missing dates count/sample
- stale_age_seconds
- quality_status distribution

### 9.2 Existing Ingestion Ops Reuse
Use existing ingestion operations suite for:
- backlog/stalled jobs
- retry and replay
- replay audit and deterministic fingerprinting
- idempotency diagnostics

### 9.3 New Ops Controls (if needed)
If reference ingestion volume materially differs from existing ingestion patterns, add endpoint-group quotas and dedicated lag views under the existing ingestion ops pattern (no direct DB runbook dependency).

## 10. Behavioral and Data Quality Requirements
1. Effective-date determinism for assignment/definition/composition resolution.
2. Composite weights must sum to 1.0 within configurable tolerance (validation only, no analytics output).
3. No duplicate dates per `(series_id, frequency)` after normalization.
4. Calendar and FX intersection policy must be explicit in response metadata.
5. Every returned dataset must include `quality_status` and lineage metadata.
6. Restatement behavior must be reproducible by `source_version` and `source_timestamp`.
7. Portfolio-benchmark assignment history must be fully preserved and point-in-time queryable.
8. If both price and return series exist, each must remain independently queryable with explicit convention metadata.
9. Classification labels used in benchmark/index contracts must resolve to canonical taxonomy values effective on `as_of_date`.
10. Unknown or deprecated classification labels must fail validation with deterministic reason codes.

## 11. Precision and Conventions (PB/WM Standard)
1. Monetary/rate/weight values must be decimal-safe in contracts.
2. Return/rate conventions must be explicit and never inferred.
3. Risk-free annualized rates must include `day_count_convention` and `compounding_convention`.
4. Responses must never mix incompatible conventions in one field.

## 12. Error Contract (Normative)
Use standard Lotus error envelope with correlation id.

Deterministic codes:
- `invalid_request`
- `resource_not_found`
- `insufficient_data`
- `unsupported_configuration`
- `source_unavailable`
- `effective_date_conflict`
- `data_quality_rejected`

## 13. Security and Access Model
1. Integration query endpoints are service-to-service only.
2. Ingestion and ops endpoints require privileged ops controls.
3. Full traceability via correlation/request/trace headers in and out.

## 14. RFC-0067 Governance Requirements
1. OpenAPI operation metadata complete (`summary`, `description`, `tags`, success/error responses).
2. Every schema attribute has meaningful description + realistic example + explicit type.
3. Canonical snake_case naming only; no aliases.
4. Regenerate lotus-core inventory in same change cycle.
5. Sync inventory to lotus-platform and run cross-app validator before merge.

## 15. Testing and Validation Strategy
1. Contract tests for each query and ingestion endpoint.
2. Determinism tests (same inputs -> same outputs).
3. Effective-dating tests (boundary and overlap cases).
4. Data quality tests (missing dates, stale series, duplicate points).
5. Docker smoke scenario: ingest assignments/definitions/series -> query all integration endpoints -> validate lineage and coverage APIs.
6. Regression suite in manifest (proposed: `reference-series-rfc`).

## 16. Implementation Slices (Proposed)

### Slice 0 - Gap Baseline and Canonical Vocabulary
- map existing capabilities vs RFC
- define canonical semantic attributes and conventions

## 17. Implementation Completion Notes
1. RFC-62 query contracts are implemented under query service `/integration/*`.
2. RFC-62 ingestion contracts are implemented under ingestion service `/ingest/*`.
3. OpenAPI metadata and DTO schema descriptions/examples are aligned to RFC-0067 governance.
4. lotus-core API vocabulary inventory has been regenerated and synced to lotus-platform.
5. Coverage and quality gates are enforced in CI using meaningful unit/integration tests aligned to test-pyramid principles.

### Slice 1 - Ingestion Contracts and Persistence Foundations
- benchmark assignment/definition/series/risk-free ingestion endpoints
- durable persistence and idempotency

### Slice 2 - Query Contracts
- assignment/definition/market-series/risk-free integration endpoints
- deterministic effective-date logic and lineage
- query service router/controller wiring for all RFC-62 integration endpoints
- service-to-service auth policy and correlation propagation for lotus-performance calls

### Slice 3 - Ops and Data Quality Surfaces
- coverage endpoints
- quality diagnostics and stale/missing indicators

### Slice 4 - Governance and Conformance
- OpenAPI completeness
- inventory sync + platform validator
- dedicated regression suite wiring

## 17. Automation Enhancements (Required)
1. Add an RFC-62 specific contract smoke harness in automation scripts.
2. Add async task profile for reference-series end-to-end validation.
3. Extend platform QA validator to include reference-series coverage and lineage checks.
4. Publish run artifact package (`json` + `md`) with endpoint responses and quality summaries.

## 18. Acceptance Criteria
1. lotus-performance has no upstream contract gap for benchmark/risk-free input acquisition.
2. lotus-core returns only raw inputs, definitions, and assignments (no derived analytics).
3. all endpoints are deterministic, lineage-complete, and ops-supportable.
4. RFC-0067 and CI quality gates pass.
5. dockerized ingestion-to-query pipeline for RFC-62 paths passes reproducibly.
6. lotus-performance integration path is query-service-only for RFC-62 contracts; no DB bypass exists in supported runbooks.
7. Benchmark and index responses expose canonical classification attributes required for attribution workflows in lotus-performance.

## 19. Open Decisions for Approval
1. Should lotus-core store both `index_price` and vendor `index_return` when provided, or require one canonical primary with optional secondary?
2. Should coverage endpoints be synchronous only, or also emit scheduled coverage snapshots to ops topic?
3. For composite benchmark rebalance, should effective dating allow same-day multi-cutover windows or enforce one active component set per day?

## 20. Final Recommendation
Proceed with this RFC boundary:
- lotus-core: authoritative benchmark/risk-free reference input platform
- lotus-performance: all derived benchmark/risk-free analytics

This gives a clean ownership model, strong PB/WM semantics, and operational reliability without reintroducing analytics drift into lotus-core.
