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

## Certified Endpoint Slice: Analytics Input Family

This certification pass covers the current strategic analytics-input contracts:

1. `POST /integration/portfolios/{portfolio_id}/analytics/reference`
2. `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
3. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`

### Route Contract Decision

These are the correct live routes. The legacy convenience reads that downstream systems sometimes
expected in earlier probes are not the governed integration contract:

1. `GET /integration/portfolios/{portfolio_id}/timeseries` is not the strategic route.
2. `GET /integration/positions/{portfolio_id}/timeseries` is not the strategic route.
3. Consumers requiring analytics input must use the `POST /integration/.../analytics/...`
   control-plane contracts so request scope, lineage, reporting-currency conversion, filters,
   dimensions, paging, and source-data metadata remain explicit and reproducible.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/analytics/reference` | `lotus-performance`, `lotus-gateway` | Correct. `lotus-performance` uses the route for stateful portfolio lifecycle/reference metadata. `lotus-gateway` uses it for workspace source context and does not attempt to compute analytics itself. |
| `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` | `lotus-performance` | Correct. This is the canonical upstream source for stateful portfolio-level return inputs. No gateway direct use was found, which is appropriate. |
| `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` | `lotus-performance`, `lotus-risk` | Correct. `lotus-performance` uses it for contribution/attribution-style sourcing. `lotus-risk` uses it for historical attribution exposure history. |

### Upstream Integration Assessment

The analytics-input family is on the correct serving plane for upstream callers:

1. query-control-plane, not query-service convenience reads
2. `POST` contract shape, not `GET`, because these routes support governed request bodies
3. explicit request lineage through `consumer_system`
4. deterministic paging via `page.page_token` and `request_scope_fingerprint`
5. reproducible currency scope via `reporting_currency`

For this family, the upstream contract is already aligned with the architecture target in
RFC-0082/RFC-0083. The remaining risk is not route placement; it is keeping economic correctness
and downstream adoption synchronized as the analytics stack evolves.

### Swagger / OpenAPI Assessment

For the analytics-input family, Swagger is now production-grade on the following dimensions:

1. route descriptions explain when to use each endpoint and who should consume it;
2. request fields and response fields carry explicit descriptions;
3. canonical examples/defaults are present across the schema family;
4. source-data product metadata and security metadata are published in OpenAPI extensions;
5. invalid-request and not-found examples are published for the operator-facing failure modes.

Automated proof now includes a recursive analytics-input schema completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py` so regressions
in field descriptions/examples are caught even when nested models change.

### Issue Disposition For This Endpoint Family

Reviewed open `lotus-core` issues tied directly to these contracts:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#233` position-timeseries missing `position_currency` | Addressed in the live contract. `PositionTimeseriesRow.position_currency` is present in the public schema, documented, and regression-covered. | Close as implemented once GitHub issue hygiene is updated. |
| `#259` need explicit flow provenance beyond plain external flow | Addressed in the live contract. `CashFlowObservation` now exposes `cash_flow_type`, `flow_scope`, and `source_classification`, with OpenAPI descriptions covering semantics. | Close as implemented once GitHub issue hygiene is updated. |
| `#250`, `#253`, `#254`, `#258`, `#260` | These are route-family economics/readiness defects rather than documentation or route-publication gaps. They require runtime validation against canonical/live scenarios before closure. | Keep open until live source-economics proof is re-run and captured. |

No new gateway issue is required from this slice. Gateway is using the strategic analytics-reference
route correctly for source context, and no duplicate or stale gateway usage of legacy analytics
paths was found during review.

## Certified Endpoint Slice: Benchmark Assignment

This certification pass covers the strategic benchmark-resolution contract:

1. `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`

### Route Contract Decision

This is the correct benchmark-assignment route for downstream consumers that need effective
portfolio-to-benchmark mapping before benchmark-aware analytics or workspace composition.

The contract is intentionally assignment-resolution only. It does not replace:

1. benchmark definition contracts,
2. benchmark composition-window contracts,
3. benchmark market-series contracts,
4. downstream benchmark math owned by `lotus-performance`.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` | `lotus-performance`, `lotus-gateway` | Correct. `lotus-performance` uses the route as benchmark context for stateful benchmark-aware analytics. `lotus-gateway` uses it for workspace composition context. |

Catalog-intended consumers also include `lotus-risk` and `lotus-report`, but no direct active code
path was found in this pass that should be overstated as live validated.

### Upstream Integration Assessment

The current implementation resolves benchmark assignment by:

1. `portfolio_id`
2. `as_of_date`
3. effective-date ordering
4. assignment-version ordering for ties

`reporting_currency` and `policy_context` are currently caller-context fields, not assignment
selection keys. This is now documented explicitly in the request schema and route description so
the public contract is truthful. The endpoint remains correctly placed on the query-control-plane.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. when to use the endpoint;
2. that assignment resolution is keyed by `portfolio_id` plus `as_of_date`;
3. that `reporting_currency` and `policy_context` do not currently alter assignment selection;
4. response field descriptions and examples for assignment-capture metadata such as
   `assignment_recorded_at` and `contract_version`.

Automated proof now includes a benchmark-assignment schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

### Issue Disposition For This Endpoint

Reviewed open benchmark-assignment-related issues:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#237` grouped benchmark analytics contract | Valid strategic follow-on. This is broader than assignment resolution and remains open. | Keep open. |
| `#246` broader benchmark source-contract hardening | Valid broader benchmark-program issue. Not a duplicate of this assignment endpoint slice. | Keep open. |
| `#249` benchmark-assignment ingest optional timestamp mismatch | Valid ingest-path issue, not a query-control-plane benchmark-assignment publication issue. | Keep open. |

No downstream migration issue is required from this slice. `lotus-performance` and `lotus-gateway`
are both calling the strategic route, and no duplicate/stale benchmark-assignment consumer path was
found during review.

## Certified Endpoint Slice: Benchmark Source Family

This certification pass covers:

1. `POST /integration/benchmarks/{benchmark_id}/composition-window`
2. `POST /integration/benchmarks/{benchmark_id}/market-series`

### Route Contract Decision

These are the correct benchmark-source contracts for downstream benchmark-aware analytics.

The contract split is intentional:

1. `composition-window` is the strategic source for cross-rebalance benchmark composition history;
2. `market-series` is the strategic source for raw component market series plus optional
   benchmark-to-target FX context;
3. downstream benchmark calculation still belongs to `lotus-performance`, not `lotus-core`;
4. single-date benchmark definition reads are useful reference context, but are not a substitute
   for long-window benchmark calculation across composition changes.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/benchmarks/{benchmark_id}/composition-window` | `lotus-performance` | Correct. `lotus-performance` uses the route in its stateful benchmark input path for rebalance-aware benchmark sourcing. |
| `POST /integration/benchmarks/{benchmark_id}/market-series` | `lotus-performance` | Correct. `lotus-performance` uses the route for component weights, raw component series, and FX-context-aware benchmark exposure/build flows. |

`lotus-risk` is catalog-intended for this family, but current live risk architecture deliberately
consumes performance-aligned benchmark exposure context rather than orchestrating core benchmark
market-series directly.

### Upstream Integration Assessment

The current benchmark-source family is aligned with the intended boundary:

1. `composition-window` returns effective-dated segments and avoids daily-expanded duplication;
2. `market-series` returns native component series plus explicit normalization metadata;
3. deterministic paging exists for large component universes via `ReferencePageRequest` and
   `ReferencePageMetadata`;
4. current `fx_rate` semantics are benchmark-currency-to-target-currency context only and should
   not be mistaken for component-to-benchmark normalization.

That last point is important enough to make explicit: the contract is strong and truthful today,
but it is not a fully normalized benchmark-engine output contract. That remains a valid future
enhancement area under the broader benchmark-source program.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. `composition-window` is the strategic cross-rebalance source;
2. `market-series` exposes native component series, not benchmark-currency-normalized component
   outputs;
3. benchmark math ownership remains with `lotus-performance`;
4. deterministic paging, request fingerprints, and normalization metadata are first-class parts of
   the public schema.

Automated proof now includes a benchmark-source schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#246` broader benchmark source hardening | Still valid as the umbrella benchmark-source program. This slice closes documentation/truth gaps but does not claim the entire benchmark-source roadmap is finished. | Keep open. |
| `#237` grouped benchmark analytics contract | Still valid. Current consumers still need some client-side grouping work on top of the lower-level source contracts. | Keep open. |

No new downstream migration issue is required from this slice. The active downstream consumer is
already using the strategic routes rather than a stale or duplicate benchmark path.

## Certified Endpoint Slice: Risk-Free Reference Family

This certification pass covers:

1. `POST /integration/reference/risk-free-series`
2. `POST /integration/reference/risk-free-series/coverage?currency=...`

### Route Contract Decision

These are the correct strategic routes for risk-free reference sourcing and readiness diagnostics.

The contract split is intentional:

1. `risk-free-series` publishes raw source series plus convention metadata and lineage;
2. `coverage` publishes readiness diagnostics for the same currency/window;
3. downstream analytics services decide whether they can proceed, fail closed, or omit dependent
   metrics based on the returned data availability.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/reference/risk-free-series` | `lotus-performance`, `lotus-risk` | Correct. Both services use the route as a source input rather than computing or inventing risk-free assumptions locally. |
| `POST /integration/reference/risk-free-series/coverage?currency=...` | `lotus-risk` | Correct. `lotus-risk` uses coverage diagnostics to produce deterministic readiness and dependency-failure behavior for rolling Sharpe. |

Gateway is not a direct caller of these endpoints. Its current follow-on issue is product-surface
messaging alignment, not route misuse.

### Upstream Integration Assessment

The current risk-free family is structurally correct and on the right serving plane. The important
contract truth is:

1. an empty `points` list means the route is reachable but usable source data is absent for the
   requested currency/window;
2. `coverage` with `total_points = 0` and null observed bounds means the same thing in readiness
   form;
3. these responses should be treated as upstream data-availability gaps, not as permission for
   downstream zero-risk-free fallback math unless a downstream service explicitly governs that mode.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. raw series publication versus readiness diagnostics;
2. that empty series responses are data-availability signals, not alternate methodology signals;
3. that zero-point coverage with null observed bounds indicates upstream data absence for the
   requested currency/window.

Automated proof now includes a risk-free schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #294` risk-free data missing for USD live window | Still valid. This is a live data-readiness defect, not a route-publication defect. | Keep open until canonical/live source data is present and revalidated. |
| `lotus-risk #77` rolling Sharpe follow-up after upstream fix | Still valid downstream follow-up issue. | Keep open until `lotus-core #294` is closed and live revalidation passes. |
| `lotus-gateway #112` stale zero-risk-free fallback wording | Still valid product-surface issue in gateway. Core route semantics are now documented truthfully, but gateway messaging still needs to align. | Keep open in gateway. |

No new downstream migration issue is required from this slice. The known work here is live data
availability and downstream messaging alignment, not route replacement.

## Certified Endpoint Slice: Simulation Session Family

This certification pass covers:

1. `POST /simulation-sessions`
2. `GET /simulation-sessions/{session_id}`
3. `DELETE /simulation-sessions/{session_id}`
4. `POST /simulation-sessions/{session_id}/changes`
5. `DELETE /simulation-sessions/{session_id}/changes/{change_id}`
6. `GET /simulation-sessions/{session_id}/projected-positions`
7. `GET /simulation-sessions/{session_id}/projected-summary`

### Route Contract Decision

These are the correct strategic control-plane routes for deterministic portfolio what-if state.

The boundary is now made explicit in Swagger and tests:

1. use these routes for sandbox state creation, mutation, and projected booked-state inspection;
2. do not use them as analytics-input publication routes;
3. do not use them for advisory recommendation, suitability, or proposal-decision logic;
4. portfolio-state projections may be consumed by downstream workflows, but recommendation logic
   remains outside `lotus-core`.

### Downstream Consumer Reality

| Route family | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `/simulation-sessions/*` | `lotus-gateway` | Correct. Gateway brokers session lifecycle and projected-state views through the control-plane base path. |
| `/integration/advisory/proposals/simulate-execution` | `lotus-advise` | Separate but related strategic route. Advise does not call raw simulation-session lifecycle routes directly for canonical proposal execution. |

`lotus-manage` remains an intended consumer in the RFC-0082 inventory, but no active direct code
path was found in this review that should be overstated as live validated.

### Upstream Integration Assessment

The simulation-session family remains on the correct serving plane and behind the correct base path:

1. query-control-plane, not query-service convenience reads;
2. control-plane sandbox lifecycle for booked-state projections;
3. deterministic projected state, not analytics output;
4. downstream advisory execution goes through the separate canonical
   `/integration/advisory/proposals/simulate-execution` route.

During this pass, a real runtime defect was also corrected: unknown `portfolio_id` on
`POST /simulation-sessions` now fails as a clean not-found error instead of falling through to a
database foreign-key violation path that could leak internal details.

### Swagger / OpenAPI Assessment

For this family, Swagger is now production-grade on the following dimensions:

1. create and projection route descriptions explain when to use the routes and when not to use
   them;
2. create-session now documents the portfolio-not-found failure mode;
3. internal server failure text is sanitized rather than exposing raw exception content;
4. the full simulation schema family is covered by a recursive documentation/example guard in
   `tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#54` simulation OpenAPI error-response gap | Addressed. Negative response codes are documented and guarded by integration tests. | Close as implemented once issue hygiene is updated. |
| `#52` unknown portfolio leaks raw DB 500 on create-session | Addressed in this slice. Service now prevalidates portfolio existence and the router returns a sanitized 404/500 contract. | Close as implemented once issue hygiene is updated. |

## Certified Endpoint Slice: Advisory Simulation Execution

This certification pass covers:

1. `POST /integration/advisory/proposals/simulate-execution`

### Route Contract Decision

This is the strategic canonical execution-projection route for `lotus-advise`.

The boundary remains explicit:

1. use it after advisory context resolution, request hashing, and idempotency orchestration;
2. do not use it as a generic simulation-session lifecycle route;
3. do not use it as a gateway-facing workspace read;
4. do not treat it as ownership of advisory recommendation logic.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/advisory/proposals/simulate-execution` | `lotus-advise` | Correct. `lotus-advise` sends the canonical contract header, request hash, idempotency key, correlation id, and validates both response header and payload contract version fields. |

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. execution projection belongs to `lotus-core`, while recommendation ownership does not;
2. error responses are published as canonical problem-details payloads;
3. problem-details fields now carry explicit examples for contract-version mismatch handling.

## Certified Endpoint Slice: Classification Taxonomy

This certification pass covers:

1. `POST /integration/reference/classification-taxonomy`

### Route Contract Decision

This is the strategic route for shared classification labels across Lotus applications.

The contract is intentionally source-owned:

1. it returns effective taxonomy entries by `as_of_date` and optional `taxonomy_scope`;
2. it is the governed source for shared labels used by performance, risk, gateway, and advise;
3. it does not synthesize missing labels for unsupported dimensions or incomplete source coverage.

That final point matters. Downstream consumers should use absence of a governed label as a visible
coverage signal, not silently invent fallback labels that blur source truth.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/reference/classification-taxonomy` | `lotus-risk`, `lotus-advise` | Correct. Both repos contain direct integration references to core-owned classification sourcing. |

`lotus-performance` and `lotus-gateway` are catalog-intended consumers and are called out in the
route contract because they rely on the same governed vocabulary, even where their current direct
code paths more often consume those labels through adjacent source contracts.

### Upstream Integration Assessment

The taxonomy route is correctly placed on the query-control-plane and currently behaves as a
truth-preserving vocabulary surface:

1. effective-dated taxonomy entries are returned without caller-side inference;
2. `taxonomy_scope` is a filter over governed source scopes, not a remapping layer;
3. missing labels remain absent, which allows downstream consumers to distinguish unsupported or
   incomplete classification coverage from valid source-owned classifications.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. the route exists to prevent local taxonomy drift;
2. `taxonomy_scope` is an optional governed-scope filter;
3. missing labels remain absent rather than synthesized;
4. the taxonomy contract version is explicit and exampled.

Automated proof now includes a classification-taxonomy schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #306` missing sector labels for canonical benchmark indices | Valid downstream-impacting classification coverage issue. The taxonomy contract itself is correct; the remaining work is source coverage and/or more explicit unsupported-dimension signaling. | Keep open. |

No new downstream migration issue is required from this slice. The active need here is classification
coverage quality, not route replacement.

## Certified Endpoint Slice: Support And Lineage Evidence

This certification pass covers the operator-evidence family around:

1. `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
2. `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings`
3. `GET /support/portfolios/{portfolio_id}/reprocessing-keys`
4. `GET /support/portfolios/{portfolio_id}/reprocessing-jobs`
5. `GET /lineage/portfolios/{portfolio_id}/securities/{security_id}`
6. `GET /lineage/portfolios/{portfolio_id}/keys`

### Route Contract Decision

These are support-plane and lineage-plane contracts, not business-calculation inputs.

They exist to publish:

1. operator evidence for blocked controls and replay workflows,
2. deterministic lineage state for recovery and investigation,
3. durable support metadata without requiring direct database access.

They should not be presented to downstream teams as calculation-grade portfolio analytics APIs.

### Downstream Consumer Reality

| Route family | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| portfolio support overview/readiness | `lotus-gateway` | Active direct use exists for workspace supportability and readiness context. |
| deeper reconciliation / replay / lineage evidence | no strong active direct consumer found in this pass | Contract is published and documented, but live product-flow evidence remains limited. Treat these routes as support-plane ready, not fully downstream-proven product surfaces. |

This is an important distinction: the endpoints are useful and intentionally governed, but the
consumer proof is still lighter than the core integration-contract families above.

### Upstream Integration Assessment

The support and lineage routes are correctly placed and modeled, but their main risk is overclaiming
runtime maturity. The current contract now states more explicitly that:

1. reconciliation runs and findings are operator evidence,
2. replay keys/jobs are operational evidence,
3. lineage routes are operational lineage evidence,
4. none of these routes should be treated as business-calculation inputs.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the operator-only boundary clearer and recursive schema-family
tests protect the evidence bundle models from documentation drift.

Automated proof now includes:

1. reconciliation-evidence schema-family completeness checks;
2. ingestion-evidence schema-family completeness checks.

### Issue Disposition For This Endpoint Family

No active GitHub issue was found that changes the current contract decision for this family.
The main follow-up remains product adoption and downstream workflow testing in repos such as
`lotus-gateway`, `lotus-manage`, and `lotus-report` when they start relying on these deeper support
surfaces directly.

## Certified Endpoint Slice: Integration Capabilities

This certification pass covers:

1. `GET /integration/capabilities`

### Route Contract Decision

This is the control-plane discovery contract for policy-resolved lotus-core capability posture.

The contract is intentionally narrow:

1. it publishes source-owned feature and workflow availability for a consumer/tenant context;
2. it is not a substitute for endpoint-specific OpenAPI or source-data product contracts;
3. callers should use the canonical snake_case query parameters `consumer_system` and `tenant_id`.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /integration/capabilities` | `lotus-gateway` | Active direct use exists via gateway platform capability aggregation and workbench composition context. |

This route is primarily a discovery/control-plane surface rather than a source-data product. The
active downstream need is real, but its job is capability publication, not domain calculation.

### Upstream Integration Assessment

The route is correctly placed and the contract is already strong. The main truth boundary worth
making explicit in this slice is canonical query naming. The route now states plainly that callers
should use snake_case `consumer_system` and `tenant_id`.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the canonical query names explicit and recursive schema-family
tests protect the capabilities response surface from documentation drift.

### Issue Disposition For This Endpoint

No lotus-core issue is open against this route at the moment.

Related downstream follow-up remains valid:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-gateway #109` | Downstream parameter-conformance issue for lotus-performance capabilities, not a lotus-core route defect. | Keep open in gateway. |
| `lotus-gateway #73` | Platform capabilities latency issue in gateway aggregation, not a lotus-core publication defect. | Keep open in gateway. |

The same certification lane now also protects the adjacent policy/effective and
instrument-enrichment contract families with recursive OpenAPI schema-family guards, so nested
policy provenance and enrichment fields do not regress silently while core-snapshot evolves.

## Certified Endpoint Slice: Core Snapshot

This certification pass covers:

1. `POST /integration/portfolios/{portfolio_id}/core-snapshot`

### Route Contract Decision

This remains the strategic state snapshot contract for downstream consumers that need governed
portfolio-state sections.

The contract boundary is now explicit in Swagger and tests:

1. use it for policy-aware baseline or simulation state;
2. use it for positions, deltas, totals, valuation context, and enrichment;
3. do not use it as a substitute for downstream performance, risk, or advisory output contracts;
4. treat it as source data publication, not analytics ownership transfer.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/core-snapshot` | `lotus-gateway`, `lotus-risk` | Correct. Gateway uses the route for workspace state sourcing, and risk uses it for concentration and rolling-Sharpe currency/valuation context. |

`lotus-manage` remains an intended consumer in the source-data catalog, but direct active code use
was not found in this pass and should not be overstated as live validated.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this route publishes portfolio-state source sections, not analytics conclusions;
2. simulation request block semantics are explicit and exampled;
3. request options and section payload semantics are explicit and exampled;
4. the full core-snapshot schema family is now protected by a recursive OpenAPI completeness guard.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #57` portfolio-scoped POST endpoint 404 gap | Already addressed for core-snapshot. The route documents 404 behavior and integration tests assert the not-found response example. | Close as implemented when issue hygiene is updated. |

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
