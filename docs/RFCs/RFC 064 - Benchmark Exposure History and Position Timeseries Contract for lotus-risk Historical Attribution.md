# RFC 064 - Benchmark Exposure History and Position Timeseries Contract for lotus-risk Historical Attribution

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-01 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core + lotus-risk integration owners |
| Depends On | RFC 062, RFC 063 |
| Related Standards | RFC-0067 API vocabulary and contract governance |
| Scope | Cross-repo |

## Executive Summary
RFC 064 originally proposed a single benchmark exposure-timeseries endpoint for lotus-risk historical attribution.  
The current lotus-core implementation uses a stronger decomposed contract model:
1. Portfolio/position analytics timeseries from RFC 063.
2. Benchmark assignment/definition/component + market/reference series from RFC 062.
3. Shared classification taxonomy and coverage diagnostics for quality controls.

This architecture is implemented and is the active standard for lotus-risk/lotus-performance integration.

## Original Requested Requirements (Preserved)
1. Reuse portfolio position timeseries contract for exposure analytics.
2. Add benchmark exposure history endpoint:
   - `POST /integration/benchmarks/{benchmark_id}/analytics/exposure-timeseries`
3. Align taxonomy/dimension semantics across portfolio and benchmark side.
4. Keep deterministic ordering/pagination semantics for large historical runs.

## What Was Originally Proposed vs What Is Implemented
### Originally Proposed
1. Single benchmark exposure-timeseries API returning benchmark exposures in one response family.

### Implemented (Current)
1. Portfolio-side exposures and timeseries are delivered via:
   - `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`
   - `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
2. Benchmark-side state is delivered via composable endpoints:
   - `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`
   - `POST /integration/benchmarks/{benchmark_id}/definition`
   - `POST /integration/benchmarks/{benchmark_id}/market-series`
   - `POST /integration/benchmarks/{benchmark_id}/return-series`
   - `POST /integration/indices/{index_id}/price-series`
   - `POST /integration/indices/{index_id}/return-series`
3. Cross-domain taxonomy/quality support:
   - `POST /integration/reference/classification-taxonomy`
   - `POST /integration/benchmarks/{benchmark_id}/coverage`
   - `POST /integration/reference/risk-free-series/coverage`

### Why the Implemented Approach Is Better
1. Separation of concerns: lotus-core stays a canonical data provider; analytics engines compute attribution/risk.
2. Better reuse: the same benchmark/reference contracts serve both lotus-risk and lotus-performance.
3. Stronger operability: coverage endpoints provide pre-run data quality gates.
4. Better scale control: callers can fetch only needed slices (assignment, definition, market series, taxonomy) instead of one oversized payload.

## Naming and Terminology Normalization
Legacy/ambiguous phrasing has been replaced with current contract terminology:
1. "benchmark exposure endpoint" -> benchmark assignment/definition/market-series contract family.
2. "point-in-time benchmark mapping" -> effective-dated benchmark assignment.
3. "index dimensions" -> classification taxonomy entries (`classification_set_id`, `dimension_name`, `dimension_value`).
4. "enriched position payload" -> separate enrichment/taxonomy contracts, avoiding duplicated enrichment in timeseries rows.

## Current Implementation Traceability
| Requirement | State | Evidence |
| --- | --- | --- |
| Portfolio and position timeseries reuse | Implemented | `src/services/query_service/app/routers/analytics_inputs.py` |
| Benchmark assignment/definition contracts | Implemented | `src/services/query_service/app/routers/integration.py`; `src/services/query_service/app/services/integration_service.py` |
| Benchmark market/reference series contracts | Implemented | `src/services/query_service/app/routers/integration.py`; `src/services/query_service/app/dtos/reference_integration_dto.py` |
| Taxonomy and coverage diagnostics | Implemented | `src/services/query_service/app/routers/integration.py` |
| Contract/service test coverage | Implemented | `tests/unit/services/query_service/routers/test_integration_router.py`; `tests/unit/services/query_service/services/test_integration_service.py`; `tests/unit/services/query_service/repositories/test_reference_data_repository.py` |

## Contract Semantics for Historical Attribution
### 1) Portfolio/Position Side (lotus-core -> downstream)
1. Position timeseries endpoint provides canonical position-level values by date.
2. Portfolio timeseries endpoint provides portfolio-level valuation/cashflow context by date.
3. Deterministic ordering and pagination semantics are provided by RFC 063 contract patterns.

### 2) Benchmark Side (lotus-core -> downstream)
1. Assignment endpoint resolves benchmark per portfolio per `as_of_date`.
2. Definition endpoint resolves effective benchmark metadata and components (index + weight).
3. Market series endpoint returns component-level series (`index_price`, `index_return`, `benchmark_return`, `component_weight`, optional `fx_rate`) in deterministic order.

### 3) Dimension Side (lotus-core -> downstream)
1. Classification taxonomy endpoint returns canonical dimension labels/scope/effective dating.
2. Benchmark/index definitions include `classification_labels` and `classification_set_id` for attribution joins.

## Quant/Analytics Mapping (Downstream Computation Model)
lotus-core does not calculate attribution. It provides deterministic inputs for lotus-risk.

Variable dictionary:
1. `w_b(i,t)` = benchmark component weight for index/instrument `i` at date `t`.
2. `w_p(i,t)` = portfolio weight for index/instrument `i` at date `t` (derived in downstream from position timeseries).
3. `r_i(t)` = component return at date `t`.
4. `r_b(t)` = benchmark return at date `t`.
5. `a(i,t)` = active exposure at date `t`.

Core attribution input formulas (executed downstream):
1. Benchmark exposure:
   `E_b(i,t) = w_b(i,t)`
2. Portfolio exposure:
   `E_p(i,t) = w_p(i,t)`
3. Active exposure:
   `a(i,t) = E_p(i,t) - E_b(i,t)`
4. Brinson-style allocation term (example):
   `Allocation(i,t) = (w_p(i,t) - w_b(i,t)) * (r_b(i,t) - r_b(t))`

These formulas are documented here for integration clarity; they are not executed in lotus-core.

## Algorithmic Flow (Implemented Integration Pattern)
1. Resolve effective benchmark assignment for portfolio/date.
2. Fetch effective benchmark definition/components.
3. Fetch portfolio/position timeseries over window.
4. Fetch benchmark market/return series over window.
5. Fetch classification taxonomy where dimension attribution is required.
6. Validate benchmark/risk-free coverage before downstream run.
7. Downstream (lotus-risk) performs exposure alignment and attribution math.

## Architecture and Design Pattern Notes
1. Decomposed integration contracts over monolithic analytics payloads.
2. Effective-dated reference model for deterministic historical replay.
3. Explicit lineage metadata on series payloads for auditability.
4. Coverage-first operational guardrails to prevent silent data quality drift.
5. Core-service boundary preserved: no performance/risk calculation inside lotus-core.

## Backward Compatibility and Migration
1. The originally proposed single endpoint was never canonicalized in production contracts.
2. Consumers should use the implemented decomposed family listed above.
3. No breaking deprecation migration is required; this RFC now reflects the active model.

## Acceptance Criteria Alignment
1. Portfolio timeseries reuse for attribution: aligned.
2. Benchmark historical exposure input availability: aligned via decomposed benchmark contracts.
3. Taxonomy alignment support: aligned.
4. Deterministic historical run support: aligned.

## Residual Follow-ups (Non-Blocking)
1. Add integration-level (not only unit-level) contract tests for benchmark integration routes in query-service dependency test suite.
2. Keep vocabulary inventory synchronized if any future benchmark contract fields evolve (RFC-0067 governance).
