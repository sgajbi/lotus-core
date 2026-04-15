# RFC-0082 / RFC-0083 Downstream Endpoint Consumer And Test Coverage Audit

Status: Draft implementation audit  
Owner: lotus-core  
Last reviewed: 2026-04-15  
Scope: query-control-plane source-data products and downstream integration posture

## Purpose

This audit records which downstream systems are expected to consume each governed lotus-core endpoint, where direct integration evidence exists, and whether the API documentation and tests are strong enough for production-grade use.

The source of truth for product identity, route family, route ownership, paging/export posture, and intended consumers remains `portfolio_common.source_data_products.SOURCE_DATA_PRODUCT_CATALOG`. This document is a review artifact layered on top of that catalog so that reviewers can reason about consumer readiness without reading every downstream repository.

## Summary

The query-control-plane API is the correct surface for cross-application integration. Downstream systems should call governed `/integration`, `/support`, and `/lineage` contracts rather than query-service convenience reads when they need analytics input, simulation state, benchmark/reference data, data-quality evidence, or operational lineage.

Current posture:

| Area | Assessment |
| --- | --- |
| Route ownership | Clear. lotus-core owns all listed source-data products. |
| Consumer metadata | Clear. Every catalog product exposes `x-lotus-source-data-product` and `x-lotus-source-data-security` in OpenAPI. |
| Swagger readability | Strong for the governed routes covered by RFC-0082/RFC-0083. Endpoint descriptions explain when to use the route, intended consumers, request attributes, response attributes, examples, and error examples. |
| Test pyramid | Strong at catalog/static guard and core integration-test levels. Direct downstream client tests exist for the active consumers found during review. |
| Platform live proof | Passed on 2026-04-15 for `PB_SG_GLOBAL_BAL_001`; see `docs/architecture/RFC-0083-platform-e2e-runtime-validation-evidence.md`. |

Important boundary reminder:

1. `lotus-core` publishes source-data products and evidence for downstream analytics workflows.
2. `lotus-core` does not own downstream performance-output contracts such as a portfolio workspace
   `Performance Snapshot`.
3. Portfolio return, benchmark return, excess return, attribution totals, and similar
   calculation outputs remain owned by the authoritative downstream analytics service, usually
   `lotus-performance`.

## Downstream Consumer Matrix

| Product | Governed route(s) | Intended consumers | Direct integration evidence reviewed | Test-pyramid posture |
| --- | --- | --- | --- | --- |
| `PortfolioStateSnapshot` | `POST /integration/portfolios/{portfolio_id}/core-snapshot` | `lotus-gateway`, `lotus-advise`, `lotus-manage`, `lotus-risk` | `lotus-gateway/src/app/clients/lotus_core_query_client.py`; `lotus-risk` RFC and live characterization references. | Core OpenAPI/catalog guards plus downstream unit/integration tests in gateway and risk. `lotus-manage` is catalog-intended and should be validated through product workflow tests when it starts consuming the route directly. |
| `PositionTimeseriesInput` | `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` | `lotus-performance`, `lotus-risk` | `lotus-performance` core integration and stateful attribution/contribution services; `lotus-risk/src/app/services/attribution_mode_adapter.py`. | Strong. Core route and schema tests, performance client tests, performance API/e2e mocked journey tests, and risk attribution adapter tests. |
| `PortfolioTimeseriesInput` | `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` | `lotus-performance`, `lotus-risk` | `lotus-performance` returns/TWR source services and canonical TWR inspection script. Risk is catalog-intended for portfolio-level analytics input, with current direct evidence stronger for position attribution and risk-free sources. | Strong for performance. Core catalog/OpenAPI tests protect the contract; risk portfolio-timeseries runtime use should be rechecked when risk portfolio-level analytics expands. |
| `PortfolioAnalyticsReference` | `POST /integration/portfolios/{portfolio_id}/analytics/reference` | `lotus-performance`, `lotus-risk` | `lotus-performance` core integration service; `lotus-gateway` uses this route as workspace source context even though gateway is not the primary analytics owner. | Strong for performance and core contract. Gateway client test covers pass-through source context. Risk should use this only where it needs analytics lifecycle/reference context, not operational holdings. |
| `MarketDataWindow` | `POST /integration/benchmarks/{benchmark_id}/market-series` | `lotus-performance`, `lotus-risk` | `lotus-performance` benchmark exposure/context services. Risk active-risk attribution currently prefers performance-aligned derived benchmark exposure where appropriate. | Strong for performance benchmark path. Core catalog/OpenAPI tests protect route shape. Risk direct market-series use should remain governed by risk RFCs to avoid duplicated benchmark engines. |
| `InstrumentReferenceBundle` | `POST /integration/instruments/enrichment-bulk`; `POST /integration/reference/classification-taxonomy` | `lotus-performance`, `lotus-risk`, `lotus-gateway`, `lotus-advise` | `lotus-advise/src/integrations/lotus_core/stateful_context.py`; `lotus-risk/src/app/services/attribution_mode_adapter.py`; gateway and performance are catalog-intended consumers for source-reference alignment. | Strong for advise and risk direct client paths. Core OpenAPI descriptions now call out all four governed consumers for classification taxonomy. |
| `BenchmarkAssignment` | `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` | `lotus-performance`, `lotus-risk`, `lotus-report` | `lotus-performance` returns and benchmark services; `lotus-gateway/src/app/clients/lotus_core_query_client.py` for workspace composition context. | Strong for performance; gateway has client-level contract proof. `lotus-report` is catalog-intended and needs product-workflow validation when direct reporting integration is active. |
| `BenchmarkConstituentWindow` | `POST /integration/benchmarks/{benchmark_id}/composition-window` | `lotus-performance`, `lotus-risk` | `lotus-performance` benchmark engine and stateful benchmark input services. | Strong for performance, including benchmark path unit/integration/characterization coverage. Risk should avoid independently recreating performance benchmark orchestration unless its RFC requires raw benchmark inputs. |
| `IndexSeriesWindow` | `POST /integration/indices/{index_id}/price-series`; `POST /integration/indices/{index_id}/return-series` | `lotus-performance`, `lotus-risk` | `lotus-performance` execution and benchmark tests reference index price series. | Strong for performance sourcing. Core OpenAPI/catalog tests protect both price and return routes. Risk direct usage should be validated when active-risk use cases require raw index series. |
| `RiskFreeSeriesWindow` | `POST /integration/reference/risk-free-series` | `lotus-performance`, `lotus-risk` | `lotus-performance` returns-series service; `lotus-risk` rolling mode adapter and live returns support. | Strong. Both performance and risk have direct tests around source retrieval/error handling, with core OpenAPI/catalog guards. |
| `ReconciliationEvidenceBundle` | `GET /support/portfolios/{portfolio_id}/reconciliation-runs`; `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings` | `lotus-performance`, `lotus-risk`, `lotus-gateway`, `lotus-manage` | Mostly governed support-plane contract evidence in lotus-core. Downstream workflows should use these routes for operator evidence, not for business calculations. | Adequate for core contract publication. More downstream product-flow tests are needed when UI/operator consumers start depending on these routes directly. |
| `DataQualityCoverageReport` | `POST /integration/benchmarks/{benchmark_id}/coverage`; `POST /integration/reference/risk-free-series/coverage` | `lotus-performance`, `lotus-risk`, `lotus-gateway`, `lotus-manage` | `lotus-risk` rolling adapter coverage calls; performance benchmark readiness paths consume benchmark coverage semantics. | Strong for risk-free coverage and core route publication. Benchmark coverage should be part of live benchmark-validation evidence before production sign-off. |
| `IngestionEvidenceBundle` | `GET /lineage/portfolios/{portfolio_id}/keys`; `GET /support/portfolios/{portfolio_id}/reprocessing-keys`; `POST /support/portfolios/{portfolio_id}/reprocessing-jobs` | `lotus-gateway`, `lotus-manage`, `lotus-report` | Core lineage and support routes are present in OpenAPI. These are operational support products rather than calculation inputs. | Adequate core route and OpenAPI proof. Downstream operator-console/report workflows need explicit tests before they can be called fully production-proven. |

## Swagger Documentation Assessment

The governed query-control-plane routes are expected to meet RFC-0067 documentation quality:

1. Endpoint summary and description explain the route's purpose, when to use it, and the primary downstream consumers.
2. Every request parameter and request-body attribute has an explicit description, type, and example through the FastAPI/Pydantic OpenAPI schema.
3. Every response attribute has an explicit description and example where the schema carries example metadata.
4. 404 and validation examples are present for important operator and integration failure modes.
5. OpenAPI operations expose `x-lotus-source-data-product` so consumers can discover product name, version, owner, route family, paging/export mode, and intended consumers.
6. OpenAPI operations expose `x-lotus-source-data-security` so consumers can discover tenant, entitlement, required capability, sensitivity, and audit expectations.

Current automated evidence:

```powershell
python scripts\openapi_quality_gate.py
python scripts\source_data_product_contract_guard.py
python scripts\analytics_input_consumer_contract_guard.py
```

These gates are necessary but not sufficient for feature sign-off. They prove contract publication quality, not live end-to-end economic correctness.

## Test Pyramid Assessment

The current test posture is intentionally layered:

| Pyramid layer | Evidence | Assessment |
| --- | --- | --- |
| Catalog/static guards | `tests/unit/scripts/test_source_data_product_contract_guard.py`, `tests/unit/scripts/test_analytics_input_consumer_contract_guard.py`, source-data catalog tests | Strong. Prevents missing extensions, incorrect route-family publication, and stale consumer metadata. |
| OpenAPI integration tests | `tests/integration/services/query_control_plane_service/test_control_plane_app.py` | Strong. Verifies route existence, excluded legacy paths, parameter descriptions, response descriptions, error examples, source-data extensions, and consumer-facing descriptions. |
| Router/service integration tests | Query-control-plane integration tests and route dependency tests | Adequate to strong for contract shape and dependency wiring. Domain-specific payload economics still require service and canonical data validation. |
| Downstream client unit tests | `lotus-performance`, `lotus-risk`, `lotus-gateway`, and `lotus-advise` client/service tests found during review | Strong for currently active consumers. Some catalog-intended consumers are intentionally future/feature dependent and should not be overstated as live validated. |
| Platform E2E | Canonical front-office runtime and live `PB_SG_GLOBAL_BAL_001` probes | Passed on 2026-04-15 for the canonical front-office flow. This does not replace PR Merge Gates or authorization/entitlement hardening proof. |

## Production-Grade Expectations

For a route to be considered production-grade, all of the following must hold:

1. The source-data product is present in `SOURCE_DATA_PRODUCT_CATALOG`.
2. OpenAPI publishes source-data and security extensions for the route.
3. Swagger descriptions explain purpose, usage, consumers, attributes, examples, and failure behavior.
4. lotus-core has targeted tests for route publication and payload shape.
5. At least one active downstream consumer has client tests for the exact path and payload contract.
6. Canonical `PB_SG_GLOBAL_BAL_001` live validation passes when the route participates in front-office calculation or UI behavior.
7. Any route used for performance, risk, or private-banking decisions has domain-level checks for economic consistency, not only JSON shape.

## Remaining Follow-Ups

1. Add downstream workflow tests as `lotus-manage` and `lotus-report` begin direct use of support/evidence products.
2. Keep `SOURCE_DATA_PRODUCT_CATALOG`, OpenAPI operation descriptions, and this audit synchronized whenever route consumers change.
3. Avoid adding downstream UI features that imply backend capability until the relevant source-data product has live validation evidence.
4. Complete PR Merge Gates and production authorization/entitlement proof before claiming full production runtime closure.
